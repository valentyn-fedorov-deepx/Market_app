from datetime import datetime
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from .session import Base


vacancy_skill_association = Table(
    "vacancy_skill_association",
    Base.metadata,
    Column("vacancy_id", ForeignKey("vacancies.id", ondelete="CASCADE"), primary_key=True),
    Column("skill_id", ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True),
)


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    vacancies = relationship("Vacancy", back_populates="category")


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    vacancies = relationship("Vacancy", back_populates="company")


class Skill(Base):
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    vacancies = relationship(
        "Vacancy",
        secondary=vacancy_skill_association,
        back_populates="skills",
    )


class Vacancy(Base):
    __tablename__ = "vacancies"
    __table_args__ = (
        UniqueConstraint("source", "source_job_id", name="uq_vacancy_source_external_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(100), nullable=False, index=True)
    source_job_id = Column(String(255), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    long_description = Column(Text, nullable=True)
    domain = Column(String(255), nullable=True)

    experience = Column(Integer, nullable=True)
    published = Column(DateTime, nullable=False, index=True)
    public_salary_min = Column(Float, nullable=True)
    public_salary_max = Column(Float, nullable=True)
    avg_salary = Column(Float, nullable=True, index=True)

    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    category = relationship("Category", back_populates="vacancies")
    company = relationship("Company", back_populates="vacancies")
    skills = relationship(
        "Skill",
        secondary=vacancy_skill_association,
        back_populates="vacancies",
    )


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(100), nullable=False, index=True)
    status = Column(String(50), nullable=False, index=True)
    message = Column(Text, nullable=True)
    records_seen = Column(Integer, default=0, nullable=False)
    records_upserted = Column(Integer, default=0, nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)


class AssistantConversation(Base):
    __tablename__ = "assistant_conversations"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), nullable=False, index=True)
    user_message = Column(Text, nullable=False)
    assistant_message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AssistantInsight(Base):
    __tablename__ = "assistant_insights"

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String(100), nullable=False, index=True)
    payload_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
