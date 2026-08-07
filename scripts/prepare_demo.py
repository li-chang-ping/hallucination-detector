import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="从本地附件生成知识库与检测输入")
    parser.add_argument("source", type=Path, help="task4_replies.json 路径")
    parser.add_argument("--output", type=Path, default=Path("data/demo"))
    args = parser.parse_args()

    replies = json.loads(args.source.read_text(encoding="utf-8"))
    knowledge = {
        "name": "0110 客服知识库",
        "description": "由本地题目附件抽取，仅用于检测演示",
        "entries": [
            {
                "id": item["id"],
                "title": f"{item['id']} 相关知识",
                "content": item["knowledge_base"],
                "metadata": {"source": "0110附件", "reply_id": item["id"]},
            }
            for item in replies
        ],
    }
    task_items = [
        {
            "id": item["id"],
            "user_question": item["user_question"],
            "system_reply": item["system_reply"],
        }
        for item in replies
    ]
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "knowledge.json").write_text(
        json.dumps(knowledge, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output / "replies.json").write_text(
        json.dumps(task_items, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"已生成 {len(task_items)} 条检测输入与 {len(knowledge['entries'])} 条知识")


if __name__ == "__main__":
    main()

