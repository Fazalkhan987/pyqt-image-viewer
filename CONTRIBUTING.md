# Contributing to Lumina

Thank you for your interest in contributing to Lumina. Bug reports, feature ideas, documentation improvements, and code contributions are welcome.

## Before you start

Please check the existing issues and pull requests before opening a new one. For larger changes, open an issue first so the proposed approach can be discussed.

## Development setup

Clone the repository and create a virtual environment:

```bash
git clone https://github.com/Fazalkhan987/pyqt-image-viewer.git
cd pyqt-image-viewer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run Lumina from the source tree:

```bash
python3 lumina.py
```

You can open an image while starting the application:

```bash
python3 lumina.py path/to/image.jpg
```

## Making changes

1. Create a branch from `main`:

   ```bash
   git checkout -b feature/your-change
   ```

2. Make focused changes that address one issue.
3. Follow the existing Python and Qt patterns.
4. Keep user-facing behavior and error messages clear.
5. Update the README or other documentation when behavior changes.
6. Test the application manually with representative images.
7. Check Python syntax before submitting:

   ```bash
   python3 -m compileall core ui utils lumina.py
   ```

8. Review your diff and commit your changes with a clear message.

## Pull requests

A good pull request should include:

- A short description of the problem and solution
- The issue number, if one exists
- Testing steps and results
- Screenshots or a short recording for visible UI changes
- Notes about any new dependencies or packaging changes

Please keep pull requests small and focused when possible. Maintainers may request changes before merging.

## Reporting bugs

When reporting a bug, include:

- Operating system and version
- Python version
- Installation method (`install.sh`, `.deb`, or source)
- Steps to reproduce the problem
- Expected and actual behavior
- Relevant terminal output or screenshots
- A sample image only when you have permission to share it

Do not include passwords, private images, or other sensitive information in issues.

## Feature requests

Describe the user problem, the proposed behavior, and why it would be useful. For UI changes, include a rough example of the desired workflow.

## License

By contributing to this project, you agree that your contribution may be distributed under the project's license.
