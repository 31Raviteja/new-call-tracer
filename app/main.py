import threading
import time
from pathlib import Path

from fastapi import FastAPI

from app.config import settings
from app.routers.calls import router as calls_router
from app.routers.history import router as history_router
from app.services.active_calls import active_call_store
from app.services.history_store import HistoryStore
from app.services.kafka_call_processor import KafkaCallProcessor
from app.services.kafka_consumer import CallKafkaConsumer

app = FastAPI(
    title="XLOGIX Call Trace Explorer",
    version="1.0.0",
)

app.include_router(calls_router)
app.include_router(history_router)


history_store = HistoryStore()

kafka_processor = KafkaCallProcessor(
    active_calls=active_call_store,
    history_store=history_store,
)


def cleanup_loop() -> None:
    """Periodically remove stale active calls."""
    while True:
        try:
            stale_events = kafka_processor.cleanup_stale_calls()

            if stale_events:
                print(f"Removed {len(stale_events)} events " "from stale calls.")

        except (RuntimeError, ValueError) as exc:
            print(f"Active call cleanup error: {exc}")

        time.sleep(60)


def start_kafka_consumer() -> None:
    """Start the Kafka consumer when Kafka is configured."""
    brokers = getattr(settings, "kafka_brokers", None)
    topic = getattr(settings, "kafka_topic", None)
    group_id = getattr(
        settings,
        "kafka_group_id",
        "xlogix-call-tracer",
    )

    if not brokers or not topic:
        return

    consumer = CallKafkaConsumer(
        brokers=brokers,
        topic=topic,
        group_id=group_id,
        on_event=kafka_processor.process,
    )

    consumer.consume()


@app.on_event("startup")
def startup() -> None:
    """Start background services."""
    cleanup_thread = threading.Thread(
        target=cleanup_loop,
        daemon=True,
        name="active-call-cleanup",
    )
    cleanup_thread.start()

    brokers = getattr(settings, "kafka_brokers", None)
    topic = getattr(settings, "kafka_topic", None)

    if not brokers or not topic:
        return

    kafka_thread = threading.Thread(
        target=start_kafka_consumer,
        daemon=True,
        name="kafka-consumer",
    )
    kafka_thread.start()


@app.get("/health")
def health() -> dict:
    """Return application health and discovered log files."""
    log_path = Path(settings.log_dir)

    files = []

    if log_path.exists() and log_path.is_dir():
        files = sorted(
            file.name
            for file in log_path.iterdir()
            if file.is_file() and file.suffix.lower() in {".log", ".txt"}
        )

    return {
        "status": "ok",
        "log_path": str(log_path),
        "files_discovered": len(files),
        "files": files,
    }
