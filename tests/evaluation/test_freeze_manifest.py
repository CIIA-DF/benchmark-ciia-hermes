"""Testes de integridade do manifesto de congelamento metodológico e blind test (TASK E4)."""

import hashlib
import json
import subprocess
from pathlib import Path

from contracts.models import Document, Process

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "evaluation" / "freeze_manifest.json"
TASKS_PATH = ROOT / "evaluation" / "tasks.json"
UV_LOCK_PATH = ROOT / "uv.lock"
GITIGNORE_PATH = ROOT / ".gitignore"
SECRET_DIR = ROOT / "evaluation" / "test_set_secret"

EXPECTED_DEV_TASK_IDS = [f"DEV-{i:03d}" for i in range(1, 16)]
EXPECTED_BLIND_TASK_IDS = [f"BLIND-{i:03d}" for i in range(1, 6)]


def test_freeze_manifest_exists_and_is_valid_json():
    assert MANIFEST_PATH.is_file(), f"Manifesto ausente: {MANIFEST_PATH}"
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert "methodological_freeze" in data


def test_freeze_manifest_uv_lock_hash_matches_disk():
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    freeze = data["methodological_freeze"]
    expected_hash = hashlib.sha256(UV_LOCK_PATH.read_bytes()).hexdigest()
    manifest_hash = freeze["environment"]["uv_lock_sha256"]
    assert manifest_hash == expected_hash, "Hash do uv.lock no manifesto diverge do arquivo real"


def test_freeze_manifest_tasks_hash_matches_disk():
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    freeze = data["methodological_freeze"]
    expected_hash = hashlib.sha256(TASKS_PATH.read_bytes()).hexdigest()
    manifest_hash = freeze["tasks"]["dev_set"]["tasks_file_sha256"]
    assert manifest_hash == expected_hash, "Hash de tasks.json no manifesto diverge do arquivo real"
    assert manifest_hash == "e566662f2279bf37ed63c56810cfb38cbab101771bfb2e0f4e2e6b0afbb103fb"


def test_freeze_manifest_registers_fifteen_dev_tasks():
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    dev_set = data["methodological_freeze"]["tasks"]["dev_set"]
    assert dev_set["count_available"] == 15
    assert dev_set["count_target"] == 15
    assert dev_set["task_ids"] == EXPECTED_DEV_TASK_IDS


def test_freeze_manifest_registers_five_secret_tasks():
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    secret_set = data["methodological_freeze"]["tasks"]["test_set_secret"]
    assert secret_set["count_available"] == 5
    assert secret_set["count_target"] == 5
    assert secret_set["task_ids"] == EXPECTED_BLIND_TASK_IDS


def test_freeze_manifest_contains_code_commit_and_ambiguity_notes():
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    commit_info = data["methodological_freeze"]["code_commit"]
    assert commit_info["frozen_commit"], "Commit congelado não pode ser vazio"
    assert "ambiguity_notes" in commit_info
    assert len(commit_info["ambiguity_notes"]) > 20


def test_freeze_manifest_adapter_prompts_hashes_are_defined():
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    prompts = data["methodological_freeze"]["adapter_prompts"]
    assert "hermes" in prompts
    assert "langgraph" in prompts
    assert len(prompts["hermes"]["prompt_sha256"]) == 64
    assert len(prompts["langgraph"]["prompt_sha256"]) == 64


def test_freeze_manifest_experimental_parameters_has_5_repetitions():
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    params = data["methodological_freeze"]["experimental_parameters"]
    assert params["repetitions_per_task"] == 5
    assert params["pairing_mode"] == "paired_identical_conditions"


def test_secret_test_set_is_ignored_by_gitignore():
    gitignore_text = GITIGNORE_PATH.read_text(encoding="utf-8")
    assert "test_set_secret" in gitignore_text, ".gitignore deve proteger test_set_secret"
    res = subprocess.run(
        ["git", "check-ignore", "evaluation/test_set_secret/tasks.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, "tasks.json secreto não está coberto por .gitignore"


def test_dev_set_tasks_contain_exactly_fifteen_homologated_tasks():
    tasks = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    assert len(tasks) == 15
    task_ids = [t.get("task_id") for t in tasks]
    assert task_ids == EXPECTED_DEV_TASK_IDS
    for task in tasks:
        assert task["split"] == "development", f"Tarefa {task.get('task_id')} fora de development"


def test_secret_test_set_contains_exactly_five_tasks():
    secret_tasks_path = SECRET_DIR / "tasks.json"
    assert secret_tasks_path.is_file(), f"Arquivo de tarefas secretas ausente: {secret_tasks_path}"
    tasks = json.loads(secret_tasks_path.read_text(encoding="utf-8"))
    assert len(tasks) == 5
    task_ids = [t.get("task_id") for t in tasks]
    assert task_ids == EXPECTED_BLIND_TASK_IDS

    required_fields = {
        "task_id",
        "split",
        "corpus_version",
        "requirements_version",
        "process_id",
        "prompt",
        "expected_evidence",
        "acceptance",
    }
    for task in tasks:
        assert task["split"] == "test_set_secret"
        assert required_fields <= task.keys()
        assert len(task["acceptance"]) >= 3


def test_secret_test_set_corpus_and_documents_are_valid():
    processes_path = SECRET_DIR / "processes.json"
    documents_path = SECRET_DIR / "documents.json"
    assert processes_path.is_file() and documents_path.is_file()

    raw_processes = json.loads(processes_path.read_text(encoding="utf-8"))
    processes = [Process.model_validate(p) for p in raw_processes]
    process_ids = {p.process_id for p in processes}
    assert {"PROC-BLIND-001", "PROC-BLIND-002"} <= process_ids

    raw_documents = json.loads(documents_path.read_text(encoding="utf-8"))
    documents = [Document.model_validate(d) for d in raw_documents]
    document_ids = {d.document_id for d in documents}
    assert {"DOC-BLIND-001", "DOC-BLIND-002", "DOC-BLIND-003"} <= document_ids

    # Validar que cada tarefa secreta referencia processo e documento existentes
    tasks = json.loads((SECRET_DIR / "tasks.json").read_text(encoding="utf-8"))
    for task in tasks:
        assert task["process_id"] in process_ids
        evidence_doc = task["expected_evidence"]["document_id"]
        assert evidence_doc in document_ids


def test_no_secret_content_in_public_tasks():
    public_tasks_text = TASKS_PATH.read_text(encoding="utf-8")
    for blind_id in EXPECTED_BLIND_TASK_IDS:
        assert blind_id not in public_tasks_text
    assert "PROC-BLIND-" not in public_tasks_text
    assert "DOC-BLIND-" not in public_tasks_text
