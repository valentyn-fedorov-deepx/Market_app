import json
import logging
import re
import uuid
import httpx
import pandas as pd
from sqlalchemy import desc, select
from sqlalchemy.orm import Session
from ..core.settings import get_settings
from ..db.models import AssistantConversation, AssistantInsight


MASCOT_NAME = "Vyz"
LOGGER = logging.getLogger(__name__)


def _safe_pct(current: float, baseline: float) -> float:
    if baseline == 0:
        return 0.0
    return ((current - baseline) / baseline) * 100


def _experience_band(years: int) -> str:
    if years <= 1:
        return "Junior"
    if years <= 4:
        return "Middle"
    if years <= 7:
        return "Senior"
    return "Lead"


class AssistantService:
    def __init__(self):
        self.settings = get_settings()

    def _build_snapshot(self, df: pd.DataFrame, category: str | None = None) -> dict:
        empty_snapshot = {
            "category": category,
            "total_vacancies": 0,
            "median_salary": 0.0,
            "avg_experience": 0.0,
            "top_skills": [],
            "fastest_growth_categories": [],
            "top_categories": [],
            "experience_bands": {},
        }
        if df.empty:
            return empty_snapshot

        scoped = df.copy()
        if category:
            scoped = scoped[scoped["category_name"] == category]
        if scoped.empty:
            return empty_snapshot

        salary_df = scoped[scoped["avg_salary"].notna()].copy()
        exploded = scoped.explode("skills")
        top_skill_counts = exploded["skills"].dropna().value_counts().head(8)
        top_skills = [{"skill": str(skill), "count": int(count)} for skill, count in top_skill_counts.items()]

        category_counts = scoped["category_name"].value_counts().head(8)
        top_categories = [{"category": str(cat), "count": int(cnt)} for cat, cnt in category_counts.items()]

        experience_bands = {"Junior": 0, "Middle": 0, "Senior": 0, "Lead": 0}
        for years, count in scoped["experience"].fillna(0).astype(int).value_counts().items():
            band = _experience_band(int(years))
            experience_bands[band] = int(experience_bands.get(band, 0) + int(count))

        monthly = (
            scoped.groupby([pd.Grouper(key="published", freq="ME"), "category_name"])
            .size()
            .reset_index(name="count")
            .sort_values(["category_name", "published"])
        )
        monthly["prev"] = monthly.groupby("category_name")["count"].shift(1)
        monthly["growth_pct"] = monthly.apply(
            lambda row: _safe_pct(row["count"], row["prev"]) if pd.notna(row["prev"]) else 0,
            axis=1,
        )
        fastest_growth = (
            monthly.groupby("category_name")["growth_pct"]
            .mean()
            .sort_values(ascending=False)
            .head(5)
            .reset_index()
            .to_dict(orient="records")
        )

        return {
            "category": category,
            "total_vacancies": int(len(scoped)),
            "median_salary": float(salary_df["avg_salary"].median()) if not salary_df.empty else 0.0,
            "avg_experience": float(scoped["experience"].mean()),
            "top_skills": top_skills,
            "fastest_growth_categories": fastest_growth,
            "top_categories": top_categories,
            "experience_bands": experience_bands,
        }

    def _build_fallback_narrative(self, snapshot: dict) -> str:
        category_text = snapshot.get("category") or "all categories"
        top_skill = snapshot["top_skills"][0]["skill"] if snapshot["top_skills"] else "нема чіткого лідера"
        growth = snapshot["fastest_growth_categories"][0]["category_name"] if snapshot["fastest_growth_categories"] else "stable"
        bands = snapshot.get("experience_bands", {})
        return (
            f"Привіт, я {MASCOT_NAME} 👋\n"
            f"Ось короткий апдейт по {category_text}:\n"
            f"- Вакансій у вибірці: {snapshot['total_vacancies']}\n"
            f"- Медіанна зарплата: ${snapshot['median_salary']:.0f}\n"
            f"- Середній досвід: {snapshot['avg_experience']:.1f} років\n"
            f"- Розбивка досвіду: Junior {bands.get('Junior', 0)}, Middle {bands.get('Middle', 0)}, Senior {bands.get('Senior', 0)}, Lead {bands.get('Lead', 0)}\n"
            f"- Найсильніший скіл зараз: {top_skill}\n"
            f"- Найшвидший ріст попиту: {growth}\n"
            f"Якщо хочеш — можу згенерувати детальний звіт із діями на 30/60/90 днів."
        )

    def _load_recent_history(self, session: Session, session_id: str | None, limit: int = 6) -> list[AssistantConversation]:
        if not session_id:
            return []
        try:
            rows = session.execute(
                select(AssistantConversation)
                .where(AssistantConversation.session_id == session_id)
                .order_by(desc(AssistantConversation.created_at))
                .limit(limit)
            ).scalars().all()
            return list(reversed(rows))
        except Exception as exc:
            LOGGER.warning("Unable to load assistant history: %s", exc)
            return []

    def _history_as_text(self, history: list[AssistantConversation]) -> str:
        if not history:
            return "Немає попередніх повідомлень."
        lines: list[str] = []
        for item in history:
            lines.append(f"Користувач: {item.user_message}")
            lines.append(f"Асистент: {item.assistant_message}")
        return "\n".join(lines)

    def _parse_experience_constraints(self, user_message: str) -> tuple[int | None, int | None]:
        msg = (user_message or "").lower()
        min_exp = None
        max_exp = None
        if any(token in msg for token in ["джун", "junior", "intern", "trainee"]):
            min_exp, max_exp = 0, 1
        elif any(token in msg for token in ["мід", "middle", "mid"]):
            min_exp, max_exp = 2, 4
        elif any(token in msg for token in ["сінь", "senior", "sr "]):
            min_exp, max_exp = 5, 7
        elif any(token in msg for token in ["lead", "principal", "staff", "архітектор"]):
            min_exp, max_exp = 8, None

        from_match = re.search(r"(?:від|from)\s*(\d{1,2})\s*(?:рок|year)", msg)
        to_match = re.search(r"(?:до|to)\s*(\d{1,2})\s*(?:рок|year)", msg)
        plus_match = re.search(r"(\d{1,2})\s*\+\s*(?:рок|year)", msg)
        exact_match = re.search(r"(\d{1,2})\s*(?:рок|year)", msg)

        if from_match:
            min_exp = int(from_match.group(1))
        if to_match:
            max_exp = int(to_match.group(1))
        if plus_match:
            min_exp = int(plus_match.group(1))
            max_exp = None
        if exact_match and from_match is None and to_match is None and plus_match is None:
            min_exp = int(exact_match.group(1))
        return min_exp, max_exp

    @staticmethod
    def _row_skills_to_list(row) -> list[str]:
        if isinstance(row, list):
            return [str(item).strip() for item in row if str(item).strip()]
        if isinstance(row, tuple):
            return [str(item).strip() for item in row if str(item).strip()]
        if isinstance(row, str):
            raw = row.strip()
            if not raw:
                return []
            if raw.startswith("[") and raw.endswith("]"):
                normalized = raw.strip("[]").replace("\"", "").replace("'", "")
                return [part.strip() for part in normalized.split(",") if part.strip()]
            return [part.strip() for part in raw.split(",") if part.strip()]
        return []

    def _infer_scope(self, df: pd.DataFrame, user_message: str, category: str | None):
        scoped = df.copy()
        msg = (user_message or "").lower()
        selected_category = None
        selected_skill = None
        if "category_name" in df.columns:
            categories = [str(cat) for cat in sorted(df["category_name"].dropna().unique().tolist())]
        else:
            categories = []
        if category and category in categories:
            selected_category = category
        else:
            for cat in sorted(categories, key=len, reverse=True):
                if cat.lower() in msg:
                    selected_category = cat
                    break

        if selected_category:
            scoped = scoped[scoped["category_name"] == selected_category]

        skill_aliases = [
            ("javascript", "JavaScript"),
            ("typescript", "TypeScript"),
            ("kubernetes", "Kubernetes"),
            ("golang", "Go"),
            ("python", "Python"),
            ("node.js", "Node.js"),
            ("node", "Node.js"),
            ("react", "React"),
            ("docker", "Docker"),
            ("java", "Java"),
            ("sql", "SQL"),
            ("aws", "AWS"),
            ("go", "Go"),
            ("ai/ml", "AI/ML"),
            ("ml", "AI/ML"),
        ]
        for alias, canonical in skill_aliases:
            if alias in msg:
                selected_skill = canonical
                break
        if selected_skill and "skills" in scoped.columns:
            scoped = scoped[
                scoped["skills"].apply(
                    lambda row: any(skill.lower() == selected_skill.lower() for skill in self._row_skills_to_list(row))
                )
            ]

        min_exp, max_exp = self._parse_experience_constraints(user_message)
        if min_exp is not None and "experience" in scoped.columns:
            scoped = scoped[scoped["experience"] >= int(min_exp)]
        if max_exp is not None and "experience" in scoped.columns:
            scoped = scoped[scoped["experience"] <= int(max_exp)]

        return scoped, selected_category, selected_skill, min_exp, max_exp

    def _build_data_answer(self, df: pd.DataFrame, user_message: str, category: str | None) -> str:
        required_cols = {"category_name", "skills", "experience", "avg_salary"}
        if df is None or df.empty or not required_cols.issubset(set(df.columns)):
            return (
                "Дані ще завантажуються в аналітичний кеш. "
                "Спробуй ще раз через 30-60 секунд — тоді дам точну відповідь з цифрами."
            )
        scoped, selected_category, selected_skill, min_exp, max_exp = self._infer_scope(df, user_message, category)
        msg = (user_message or "").lower()
        scope_parts = []
        if selected_category:
            scope_parts.append(f"категорія: {selected_category}")
        if selected_skill:
            scope_parts.append(f"навичка: {selected_skill}")
        if min_exp is not None or max_exp is not None:
            if max_exp is None:
                scope_parts.append(f"досвід від {min_exp}+ років")
            elif min_exp is None:
                scope_parts.append(f"досвід до {max_exp} років")
            elif min_exp == max_exp:
                scope_parts.append(f"досвід {min_exp} років")
            else:
                scope_parts.append(f"досвід {min_exp}-{max_exp} років")
        scope_label = ", ".join(scope_parts) if scope_parts else "весь ринок"

        if scoped.empty:
            return f"За умовами ({scope_label}) даних не знайдено. Спробуй послабити фільтр категорії/досвіду/навички."

        salary_df = scoped[scoped["avg_salary"].notna()].copy()

        if any(word in msg for word in ["зарплат", "salary", "дохід", "компенсац"]):
            if salary_df.empty:
                return f"За умовами ({scope_label}) є {len(scoped)} вакансій, але без salary-даних."
            median = float(salary_df["avg_salary"].median())
            p25 = float(salary_df["avg_salary"].quantile(0.25))
            p75 = float(salary_df["avg_salary"].quantile(0.75))
            return (
                f"По зрізу ({scope_label}): вакансій {len(scoped)}, salary-точок {len(salary_df)}. "
                f"Медіанна зарплата ≈ ${median:,.0f}, міжквартильний діапазон ${p25:,.0f}–${p75:,.0f}."
            )

        if any(word in msg for word in ["навич", "skill", "стек", "технолог"]):
            normalized = scoped.copy()
            normalized["skills"] = normalized["skills"].apply(self._row_skills_to_list)
            exploded = normalized.explode("skills")
            top = exploded["skills"].dropna().value_counts().head(8)
            if top.empty:
                return f"За умовами ({scope_label}) не вистачає структурованих skill-даних."
            items = ", ".join(f"{skill} ({int(count)})" for skill, count in top.items())
            return f"Топ навички для ({scope_label}): {items}."

        if any(word in msg for word in ["досвід", "junior", "middle", "senior", "lead", "джун", "мід", "сінь"]):
            bands = {"Junior": 0, "Middle": 0, "Senior": 0, "Lead": 0}
            for years, count in scoped["experience"].fillna(0).astype(int).value_counts().items():
                bands[_experience_band(int(years))] += int(count)
            return (
                f"Розбивка досвіду для ({scope_label}): "
                f"Junior={bands['Junior']}, Middle={bands['Middle']}, Senior={bands['Senior']}, Lead={bands['Lead']}."
            )

        if any(word in msg for word in ["категор", "category", "напрям"]):
            top_categories = scoped["category_name"].value_counts().head(8)
            items = ", ".join(f"{cat} ({int(cnt)})" for cat, cnt in top_categories.items())
            return f"Топ категорії у зрізі ({scope_label}): {items}."

        summary_snapshot = self._build_snapshot(scoped, category=selected_category)
        return self._build_fallback_narrative(summary_snapshot)

    def _is_market_related(self, user_message: str) -> bool:
        msg = (user_message or "").lower()
        market_keywords = [
            "зарплат",
            "salary",
            "дохід",
            "ваканс",
            "ринок",
            "попит",
            "досвід",
            "junior",
            "middle",
            "senior",
            "lead",
            "джун",
            "мід",
            "сінь",
            "категор",
            "напрям",
            "скі",
            "skill",
            "стек",
            "технолог",
            "тренд",
            "анал",
        ]
        return any(keyword in msg for keyword in market_keywords)

    def _build_conversational_fallback(self, user_message: str, snapshot: dict) -> str:
        msg = (user_message or "").lower()
        total = int(snapshot.get("total_vacancies", 0))
        median = float(snapshot.get("median_salary", 0.0))
        if any(token in msg for token in ["привіт", "hello", "hi", "добр", "віта"]):
            return (
                f"Привіт! Я {MASCOT_NAME}. Можу поговорити і допомогти з аналізом IT-ринку. "
                f"Зараз у базі {total} вакансій. Питай про зарплати, скіли або попит по рівнях."
            )
        if any(token in msg for token in ["дякую", "спасиб", "thx", "thanks"]):
            return "Завжди радий допомогти. Можу ще порівняти категорії або дати зріз по junior/middle/senior."
        if any(token in msg for token in ["хто ти", "what are you", "що ти вмієш", "що ти можеш"]):
            return (
                f"Я {MASCOT_NAME}, асистент цього застосунку. "
                f"Можу вести діалог і давати відповіді по ринку на основі ваших даних: вакансії, зарплати, скіли, досвід."
            )
        return (
            "Можу підтримати розмову і відповісти по ринку праці в IT. "
            f"Наприклад, зараз медіанна зарплата по поточному зрізу близько ${median:,.0f}. "
            "Скажи, що саме порівняти або проаналізувати."
        )

    def _build_chat_prompt(
        self,
        user_message: str,
        history_text: str,
        snapshot: dict,
        deterministic_answer: str,
        market_related: bool,
    ) -> str:
        if not market_related:
            return (
                f"Ти дружній AI-асистент {MASCOT_NAME}.\n"
                "Відповідай українською, коротко, природно та без шаблонів.\n"
                "Підтримуй живу розмову, враховуючи історію діалогу.\n\n"
                f"Історія діалогу:\n{history_text}\n\n"
                f"Останнє повідомлення користувача:\n{user_message}"
            )
        return (
            f"Ти дружній AI-асистент {MASCOT_NAME} для IT market analytics застосунку.\n"
            "Відповідай українською, природно і без шаблонних фраз.\n"
            "Підтримуй діалог і враховуй попередні повідомлення.\n"
            "Якщо питання про ринок праці, не вигадуй числа: використовуй лише факти з блоку 'Детермінована відповідь'.\n"
            "Якщо питання загальне або small-talk — відповідай по-людськи, коротко і дружньо.\n"
            f"Питання про ринок: {'так' if market_related else 'ні'}\n\n"
            f"Історія діалогу:\n{history_text}\n\n"
            f"Контекст JSON:\n{json.dumps(snapshot, ensure_ascii=False)}\n\n"
            f"Детермінована відповідь (фактична база):\n{deterministic_answer}\n\n"
            f"Останнє повідомлення користувача:\n{user_message}"
        )

    def _llm_timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=10.0,
            read=float(self.settings.ollama_timeout_seconds),
            write=30.0,
            pool=30.0,
        )

    def _call_ollama_generate(self, prompt: str) -> str | None:
        endpoint = f"{self.settings.ollama_base_url.rstrip('/')}/api/generate"
        payload = {
            "model": self.settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.settings.assistant_temperature,
                "num_predict": self.settings.assistant_max_tokens,
            },
        }
        try:
            with httpx.Client(timeout=self._llm_timeout()) as client:
                response = client.post(endpoint, json=payload)
                response.raise_for_status()
                data = response.json()
                text = (data.get("response") or "").strip()
                return text or None
        except Exception as exc:
            LOGGER.warning("LLM ollama request failed: %s", exc)
            return None

    def _call_openai_compatible(self, prompt: str) -> str | None:
        base_url = (self.settings.llm_api_base_url or "").strip()
        model = (self.settings.llm_api_model or "").strip()
        api_key = (self.settings.llm_api_key or "").strip()
        if not base_url or not model or not api_key:
            return None
        endpoint = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if self.settings.llm_api_referer:
            headers["HTTP-Referer"] = self.settings.llm_api_referer
        if self.settings.llm_api_title:
            headers["X-Title"] = self.settings.llm_api_title
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.settings.assistant_temperature,
            "max_tokens": self.settings.assistant_max_tokens,
        }
        try:
            with httpx.Client(timeout=self._llm_timeout()) as client:
                response = client.post(endpoint, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                choices = data.get("choices") or []
                if not choices:
                    return None
                message = choices[0].get("message") or {}
                content = message.get("content")
                if isinstance(content, list):
                    text_parts = [str(item.get("text") or "") for item in content if isinstance(item, dict)]
                    content = " ".join(part for part in text_parts if part).strip()
                if not isinstance(content, str):
                    return None
                content = content.strip()
                return content or None
        except Exception as exc:
            LOGGER.warning("LLM openai-compatible request failed: %s", exc)
            return None

    def _call_ollama(self, prompt: str) -> str | None:
        if not self.settings.assistant_llm_enabled:
            return None
        if not prompt or not prompt.strip():
            return None
        provider = (self.settings.llm_provider or "ollama").strip().lower()
        if provider in {"openai_compatible", "openai", "openrouter", "groq"}:
            return self._call_openai_compatible(prompt)
        return self._call_ollama_generate(prompt)

    def generate_insights(self, session: Session, df: pd.DataFrame, category: str | None = None) -> dict:
        snapshot = self._build_snapshot(df, category=category)
        fallback = self._build_fallback_narrative(snapshot)

        prompt = (
            "Ти AI-аналітик IT-ринку. На базі JSON дай 5 коротких інсайтів українською мовою. "
            "Кожен інсайт: заголовок + 1-2 речення + практичний крок. "
            f"JSON:\n{json.dumps(snapshot, ensure_ascii=False)}"
        )
        llm_text = self._call_ollama(prompt)

        response = {
            "mascot_name": MASCOT_NAME,
            "snapshot": snapshot,
            "narrative": llm_text or fallback,
            "llm_used": bool(llm_text),
        }
        session.add(
            AssistantInsight(
                kind="insights",
                payload_json=json.dumps(response, ensure_ascii=False),
            )
        )
        session.commit()
        return response

    def generate_report(
        self,
        session: Session,
        df: pd.DataFrame,
        category: str | None = None,
        horizon_days: int = 90,
    ) -> dict:
        snapshot = self._build_snapshot(df, category=category)
        fallback_report = (
            f"# Звіт від {MASCOT_NAME}\n"
            f"## Сегмент\n"
            f"{category or 'All categories'}\n"
            f"## Ключові показники\n"
            f"- Вакансії: {snapshot['total_vacancies']}\n"
            f"- Медіанна зарплата: ${snapshot['median_salary']:.0f}\n"
            f"- Середній досвід: {snapshot['avg_experience']:.1f}\n"
            f"## Рекомендації на {horizon_days} днів\n"
            f"1. Оновити стек за топ-скілами сегмента.\n"
            f"2. Трекати динаміку вакансій по тижнях.\n"
            f"3. Перевіряти salary-діапазони в топ-категоріях росту.\n"
        )

        prompt = (
            "Ти AI-аналітик IT-ринку. Підготуй структурований короткий markdown-звіт українською: "
            "резюме, ризики, можливості, 5 дій на 30/60/90 днів. "
            f"Горизонт днів: {horizon_days}. JSON:\n{json.dumps(snapshot, ensure_ascii=False)}"
        )
        llm_text = self._call_ollama(prompt)
        report_text = llm_text or fallback_report

        response = {
            "mascot_name": MASCOT_NAME,
            "category": category,
            "horizon_days": horizon_days,
            "report_markdown": report_text,
            "llm_used": bool(llm_text),
        }
        session.add(
            AssistantInsight(
                kind="report",
                payload_json=json.dumps(response, ensure_ascii=False),
            )
        )
        session.commit()
        return response

    def chat(
        self,
        session: Session,
        df: pd.DataFrame,
        user_message: str,
        session_id: str | None = None,
        category: str | None = None,
    ) -> dict:
        snapshot = self._build_snapshot(df, category=category)
        resolved_session_id = session_id or str(uuid.uuid4())
        history = self._load_recent_history(session=session, session_id=resolved_session_id, limit=6)
        history_text = self._history_as_text(history)
        market_related = self._is_market_related(user_message)
        deterministic_answer = self._build_data_answer(df=df, user_message=user_message, category=category)
        fallback_answer = (
            deterministic_answer
            if market_related
            else self._build_conversational_fallback(user_message=user_message, snapshot=snapshot)
        )
        prompt = self._build_chat_prompt(
            user_message=user_message,
            history_text=history_text,
            snapshot=snapshot,
            deterministic_answer=deterministic_answer,
            market_related=market_related,
        )
        llm_text = self._call_ollama(prompt)
        if llm_text and market_related and not any(ch.isdigit() for ch in llm_text):
            answer = f"{llm_text}\n\nФакти зі зрізу: {deterministic_answer}"
        else:
            answer = llm_text or fallback_answer
        saved_to_history = True
        try:
            session.add(
                AssistantConversation(
                    session_id=resolved_session_id,
                    user_message=user_message,
                    assistant_message=answer,
                )
            )
            session.commit()
        except Exception:
            session.rollback()
            saved_to_history = False

        return {
            "session_id": resolved_session_id,
            "mascot_name": MASCOT_NAME,
            "message": answer,
            "llm_used": bool(llm_text),
            "saved_to_history": saved_to_history,
        }
