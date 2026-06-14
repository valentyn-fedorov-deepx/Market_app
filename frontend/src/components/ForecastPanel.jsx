import { useEffect, useState } from 'react';
import {
    Alert,
    Box,
    Chip,
    Divider,
    LinearProgress,
    MenuItem,
    Paper,
    Stack,
    TextField,
    Tooltip,
    Typography,
} from '@mui/material';
import PsychologyRoundedIcon from '@mui/icons-material/PsychologyRounded';
import { motion } from 'framer-motion';
import Chart from './Chart';

const MODEL_OPTIONS = [
    { value: 'auto', label: 'Авто (найкраща)' },
    { value: 'prophet', label: 'Prophet' },
    { value: 'linear_trend', label: 'Лінійний тренд' },
    { value: 'seasonal_naive', label: 'Сезонний наївний' },
];

const TRAINING_STEPS = [
    'Готуємо часовий ряд (місячна агрегація)…',
    'Навчаємо модель на історії…',
    'Бектест на відкладених місяцях…',
    'Будуємо прогноз на майбутнє…',
];

const TrainingLoader = ({ model }) => {
    const [step, setStep] = useState(0);
    useEffect(() => {
        const id = setInterval(() => setStep((prev) => (prev + 1) % TRAINING_STEPS.length), 750);
        return () => clearInterval(id);
    }, []);
    return (
        <Box sx={{ py: 5, px: 2, textAlign: 'center' }}>
            <motion.div
                animate={{ rotate: [0, 8, -8, 0], scale: [1, 1.08, 1] }}
                transition={{ duration: 1.4, repeat: Infinity }}
                style={{ display: 'inline-flex' }}
            >
                <PsychologyRoundedIcon sx={{ fontSize: 54, color: '#90caf9' }} />
            </motion.div>
            <Typography variant="h6" sx={{ mt: 1.5 }}>
                Модель «{model}» навчається…
            </Typography>
            <Box sx={{ maxWidth: 460, mx: 'auto', mt: 2 }}>
                <LinearProgress />
            </Box>
            <Stack spacing={0.5} sx={{ mt: 2, alignItems: 'center' }}>
                {TRAINING_STEPS.map((label, idx) => (
                    <Typography
                        key={label}
                        variant="body2"
                        sx={{ opacity: idx === step ? 1 : 0.4, fontWeight: idx === step ? 600 : 400, transition: 'opacity .3s' }}
                    >
                        {idx <= step ? '✓ ' : '• '}
                        {label}
                    </Typography>
                ))}
            </Stack>
        </Box>
    );
};

const DiagnosticChips = ({ diagnostics }) => {
    if (!diagnostics) return null;
    const entries = [];
    if (diagnostics.aic != null) entries.push(`AIC: ${diagnostics.aic}`);
    if (diagnostics.bic != null) entries.push(`BIC: ${diagnostics.bic}`);
    if (diagnostics.iterations != null && diagnostics.iterations > 0) entries.push(`Ітерацій оптимізації: ${diagnostics.iterations}`);
    if (diagnostics.seasonal_order) entries.push(`Seasonal order: ${diagnostics.seasonal_order}`);
    if (diagnostics.slope != null) entries.push(`Нахил тренду: ${diagnostics.slope}`);
    if (diagnostics.intercept != null) entries.push(`Перетин: ${diagnostics.intercept}`);
    if (diagnostics.changepoints != null) entries.push(`Changepoints: ${diagnostics.changepoints}`);
    if (diagnostics.season_length != null) entries.push(`Сезон: ${diagnostics.season_length} міс.`);
    return entries.map((text) => <Chip key={text} size="small" variant="outlined" label={text} />);
};

const ForecastPanel = ({ forecast, loading, category, model = 'auto', onModelChange }) => {
    const training = forecast?.training;
    const holdout = training?.holdout;
    const available = forecast?.available_models || [];

    const modelSelect = (
        <TextField
            select
            size="small"
            label="Модель прогнозу"
            value={model}
            onChange={(e) => onModelChange?.(e.target.value)}
            sx={{ minWidth: 200 }}
        >
            {MODEL_OPTIONS.map((opt) => {
                const enabled = opt.value === 'auto' || available.length === 0 || available.includes(opt.value);
                return (
                    <MenuItem key={opt.value} value={opt.value} disabled={!enabled}>
                        {opt.label}
                        {!enabled ? ' (недоступна тут)' : ''}
                    </MenuItem>
                );
            })}
        </TextField>
    );

    return (
        <Paper className="glass-paper" component={motion.div} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} sx={{ p: 2.2, minHeight: 460 }}>
            <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} spacing={1.5} sx={{ mb: 1 }}>
                <Typography variant="h5">Прогноз попиту{category ? ` — "${category}"` : ''}</Typography>
                {modelSelect}
            </Stack>

            {loading ? <TrainingLoader model={model === 'auto' ? 'авто' : model} /> : null}

            {!loading && !forecast ? (
                <Alert severity="info" sx={{ mt: 2 }}>
                    Недостатньо історичних даних для прогнозу в цьому зрізі. Спробуй іншу категорію або послаб фільтри.
                </Alert>
            ) : null}

            {!loading && forecast ? (
                <>
                    {forecast.fallback ? (
                        <Alert severity="warning" sx={{ mb: 1.5 }}>
                            Модель «{forecast.requested_model}» недоступна для цього зрізу — показано «{forecast.model_used}».
                        </Alert>
                    ) : null}

                    <Box sx={{ height: 380 }}>
                        <Chart
                            data={[
                                {
                                    x: forecast.dates,
                                    y: forecast.confidence_upper,
                                    fill: 'tonexty',
                                    fillcolor: 'rgba(144, 202, 249, 0.2)',
                                    line: { color: 'transparent' },
                                    name: 'Довірчий інтервал',
                                    showlegend: false,
                                },
                                {
                                    x: forecast.dates,
                                    y: forecast.confidence_lower,
                                    line: { color: 'transparent' },
                                    showlegend: false,
                                    name: 'Довірчий інтервал',
                                },
                                {
                                    x: forecast.historical_dates,
                                    y: forecast.historical_demand,
                                    mode: 'lines',
                                    name: 'Історія (факт)',
                                    line: { color: '#9aa3b4' },
                                },
                                {
                                    x: forecast.dates,
                                    y: forecast.predicted_demand,
                                    mode: 'lines',
                                    name: 'Прогноз',
                                    line: { color: '#90caf9', width: 3 },
                                },
                            ]}
                            layout={{ title: 'Динаміка та прогноз кількості вакансій', autosize: true }}
                        />
                    </Box>

                    {training ? (
                        <Box sx={{ mt: 1.5 }}>
                            <Divider sx={{ mb: 1.5 }} />
                            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
                                <PsychologyRoundedIcon fontSize="small" sx={{ color: '#90caf9' }} />
                                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                                    Як навчалася модель
                                </Typography>
                            </Stack>
                            <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', gap: 1, mb: 1.5 }}>
                                <Chip size="small" color="primary" label={`Модель: ${forecast.model_used}`} />
                                {training.backtest?.mape != null ? (
                                    <Tooltip title="Точність на відкладеній вибірці = 100% − MAPE">
                                        <Chip size="small" color="success" label={`Точність: ${Math.max(0, 100 - training.backtest.mape).toFixed(1)}%`} />
                                    </Tooltip>
                                ) : null}
                                <Chip size="small" label={`Навчальних точок: ${training.samples}`} />
                                <Tooltip title="Реальний час підбору параметрів моделі на сервері">
                                    <Chip size="small" label={`Час навчання: ${training.train_time_ms} мс`} />
                                </Tooltip>
                                {training.backtest?.mae != null ? <Chip size="small" variant="outlined" label={`MAE (holdout): ${training.backtest.mae}`} /> : null}
                                {training.backtest?.mape != null ? <Chip size="small" variant="outlined" label={`MAPE: ${training.backtest.mape}%`} /> : null}
                                <DiagnosticChips diagnostics={training.diagnostics} />
                            </Stack>

                            {holdout && holdout.dates?.length ? (
                                <>
                                    <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                                        Бектест: модель навчили на ранніх даних і попросили передбачити останні{' '}
                                        {training.backtest?.test_size} міс., яких вона <b>не бачила</b>. Збіг ліній = модель справді
                                        вчиться на даних, а не показує фіксовані числа.
                                    </Typography>
                                    <Box sx={{ height: 300 }}>
                                        <Chart
                                            data={[
                                                {
                                                    x: holdout.dates,
                                                    y: holdout.actual,
                                                    mode: 'lines+markers',
                                                    name: 'Факт (відкладені)',
                                                    line: { color: '#aab2c5' },
                                                },
                                                {
                                                    x: holdout.dates,
                                                    y: holdout.predicted,
                                                    mode: 'lines+markers',
                                                    name: 'Прогноз моделі',
                                                    line: { color: '#66bb6a', width: 3, dash: 'dot' },
                                                },
                                            ]}
                                            layout={{ title: 'Перевірка на відкладеній вибірці (out-of-sample)', autosize: true }}
                                        />
                                    </Box>
                                </>
                            ) : (
                                <Typography variant="body2" color="text.secondary">
                                    Для бектесту замало історії (потрібно ≥30 місяців) — показано пряме навчання на всьому ряді.
                                </Typography>
                            )}
                        </Box>
                    ) : null}
                </>
            ) : null}
        </Paper>
    );
};

export default ForecastPanel;
