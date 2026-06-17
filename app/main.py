import argparse

from app.agent import run_agent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="World Cup LangChain Agent")
    parser.add_argument(
        "question",
        nargs="?",
        default="生成今天世界杯战报",
        help="Question to ask the agent.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    answer = run_agent(args.question)
    print(answer)


if __name__ == "__main__":
    main()
