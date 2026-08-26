from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from app.services.knowledge_agent import clear_knowledge_memory_cache, status


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pre-indexa as fontes Markdown e PDF da base de conhecimento do Skinner."
    )
    parser.add_argument(
        "--pdf-dir",
        action="append",
        default=[],
        help="Diretorio de PDFs. Pode ser informado mais de uma vez.",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.pdf_dir:
        resolved = [str(Path(value).expanduser().resolve()) for value in args.pdf_dir]
        os.environ["SKINNER_KNOWLEDGE_PDF_DIRS"] = os.pathsep.join(resolved)

    started = time.perf_counter()
    clear_knowledge_memory_cache()
    payload = status()
    payload["duracao_indexacao_segundos"] = round(time.perf_counter() - started, 2)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
