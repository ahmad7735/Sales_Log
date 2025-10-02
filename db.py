import os
import streamlit as st
from sqlalchemy import create_engine, text

def get_engine():
    # Streamlit Secrets first; fallback to env var
    url = st.secrets["database"]["url"] if "database" in st.secrets else os.environ["DATABASE_URL"]
    # neon needs sslmode=require (already in URL)
    return create_engine(url, pool_pre_ping=True)

def init_schema():
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS saleslog (
            QuoteID      INTEGER PRIMARY KEY,
            Client       TEXT,
            QuotedPrice  DOUBLE PRECISION DEFAULT 0,
            Status       TEXT,
            SalesRep     TEXT,
            "Deposit%"   DOUBLE PRECISION DEFAULT 0,
            DepositPaid  DOUBLE PRECISION DEFAULT 0,
            SentDate     DATE,
            JobType      TEXT
        );
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS collections (
            id           BIGSERIAL PRIMARY KEY,
            QuoteID      INTEGER REFERENCES saleslog(QuoteID) ON DELETE CASCADE,
            CollectionDate DATE,
            Client       TEXT,
            DepositPaid  DOUBLE PRECISION DEFAULT 0,
            BalanceDue   DOUBLE PRECISION DEFAULT 0,
            Status       TEXT
        );
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS assignments (
            id           BIGSERIAL PRIMARY KEY,
            QuoteID      INTEGER REFERENCES saleslog(QuoteID) ON DELETE CASCADE,
            Client       TEXT,
            CrewMember   TEXT,
            StartDate    DATE,
            EndDate      DATE,
            Payment      DOUBLE PRECISION DEFAULT 0,
            DaysTaken    INTEGER DEFAULT 0,
            Notes        TEXT,
            Completed    BOOLEAN DEFAULT FALSE,
            TaskStatus   TEXT
        );
        """))
