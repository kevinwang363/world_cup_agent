import argparse

from app.agent import run_agent, run_chat_loop


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="World Cup LangChain Agent")
    parser.add_argument(
        "question",
        nargs="?",
        default="生成今天世界杯战报",
        help="Question to ask the agent.",
    )
    parser.add_argument(
        "--chat",
        action="store_true",
        help="Start an interactive multi-turn chat session.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.chat:
        run_chat_loop()
        return

    answer = run_agent(args.question)
    print(answer)


if __name__ == "__main__":
    main()
