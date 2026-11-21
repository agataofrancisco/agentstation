"""Processo filho dos testes de recuperacao. Modo `start` (pode morrer por crash) ou `resume`.

Configuracao vem do ambiente (DATABASE_URL, CHECKPOINT_URL, CRASH_AT_NODE, ...), como em producao.
"""

import json
import sys

from backend.app.workers import jobs
from backend.app.workers.runtime import configure


def main() -> None:
    mode, task_id = sys.argv[1], sys.argv[2]
    from backend.app.config import get_settings

    rt = configure(get_settings())
    if mode == "start":
        outcome = jobs.run_task_job(task_id, rt)
    elif mode == "resume":
        outcome = jobs.run_task_job(task_id, rt)
    else:
        raise SystemExit("modo desconhecido")
    print(json.dumps({"outcome": outcome}), flush=True)


if __name__ == "__main__":
    main()
