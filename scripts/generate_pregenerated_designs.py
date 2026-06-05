from app.services.pregenerated import generate_all_project_libraries


def main() -> None:
    outputs = generate_all_project_libraries(count=5000, force=True)
    for project_id, path in outputs.items():
        print(f"{project_id}: {path}")


if __name__ == "__main__":
    main()
