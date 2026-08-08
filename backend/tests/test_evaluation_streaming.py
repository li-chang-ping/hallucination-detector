import json
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.models import DetectionItem, DetectionTask, Evaluation, TaskStatus
from app.routers import evaluations as evaluation_router
from app.services.evaluations import record_evaluation_progress


def test_evaluation_returns_accepted_and_streams_persisted_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        task = DetectionTask(
            name="流式评测测试",
            status=TaskStatus.COMPLETED,
            model_name="deepseek-v4-flash",
            total_count=1,
            completed_count=1,
        )
        session.add(task)
        session.flush()
        session.add(
            DetectionItem(
                task_id=task.id,
                input_id="h01",
                position=0,
                user_question="支持退货吗？",
                system_reply="支持七天无理由退货。",
                status="completed",
                is_hallucination=False,
            )
        )
        session.commit()
        task_id = task.id

    def override_db() -> Generator[Session]:
        with Session(engine, expire_on_commit=False) as session:
            yield session

    async def complete_in_background(evaluation_id: str) -> None:
        with Session(engine, expire_on_commit=False) as session:
            evaluation = session.get(Evaluation, evaluation_id)
            assert evaluation is not None
            record_evaluation_progress(
                session,
                evaluation,
                "指标计算完成，正在识别漏检和误报",
                20,
                status="running",
            )
            record_evaluation_progress(
                session,
                evaluation,
                "未发现漏检或误报，比较完成",
                100,
                status="completed",
            )

    monkeypatch.setattr(evaluation_router, "run_evaluation_insights", complete_in_background)
    monkeypatch.setattr(
        evaluation_router,
        "SessionLocal",
        lambda: Session(engine, expire_on_commit=False),
    )
    application = FastAPI()
    application.include_router(evaluation_router.router, prefix="/api/v1")
    application.dependency_overrides[get_db] = override_db
    ground_truth = [{"id": "h01", "is_hallucination": False, "detail": ""}]

    with TestClient(application) as client:
        response = client.post(
            f"/api/v1/evaluations/tasks/{task_id}",
            files={"file": ("ground-truth.json", json.dumps(ground_truth), "application/json")},
        )
        assert response.status_code == 202
        evaluation_id = response.json()["id"]
        assert response.json()["insight_stage"] == "人工标注校验完成，已创建后台评测"

        stream = client.get(f"/api/v1/evaluations/{evaluation_id}/events")
        assert stream.headers["content-type"].startswith("text/event-stream")
        assert "指标计算完成，正在识别漏检和误报" in stream.text
        assert "未发现漏检或误报，比较完成" in stream.text
        assert "event: complete" in stream.text


def test_replies_file_is_rejected_with_clear_ground_truth_message() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        task = DetectionTask(
            name="文件类型提示测试",
            status=TaskStatus.COMPLETED,
            model_name="deepseek-v4-flash",
            total_count=1,
            completed_count=1,
        )
        session.add(task)
        session.flush()
        session.add(
            DetectionItem(
                task_id=task.id,
                input_id="h01",
                position=0,
                user_question="支持退货吗？",
                system_reply="支持七天无理由退货。",
                status="completed",
                is_hallucination=False,
            )
        )
        session.commit()
        task_id = task.id

    def override_db() -> Generator[Session]:
        with Session(engine, expire_on_commit=False) as session:
            yield session

    application = FastAPI()
    application.include_router(evaluation_router.router, prefix="/api/v1")
    application.dependency_overrides[get_db] = override_db
    replies = [{"id": "h01", "user_question": "支持退货吗？", "system_reply": "支持。"}]

    with TestClient(application) as client:
        response = client.post(
            f"/api/v1/evaluations/tasks/{task_id}",
            files={"file": ("replies.json", json.dumps(replies), "application/json")},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "上传的是检测回复数据，不是人工标注结果；"
        "请上传每条包含 id、is_hallucination、hallucination_type 和 detail 的 JSON"
    )
