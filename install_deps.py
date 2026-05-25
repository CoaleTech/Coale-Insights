#!/usr/bin/env python3
"""
Insights Dependency Installer
==============================
One-stop script to install all Insights optional dependencies with OS-aware
system library checks, Python version compatibility handling, and verification.

Usage:
    python install_deps.py              # Install all optional groups
    python install_deps.py --group ml   # Install only ML group
    python install_deps.py --verify     # Verify existing installation
"""

import argparse
import os
import platform
import subprocess
import sys


def run(cmd, check=True, capture=False):
    """Run a shell command."""
    kwargs = {"shell": True, "check": check}
    if capture:
        kwargs["capture_output"] = True
        kwargs["text"] = True
    return subprocess.run(cmd, **kwargs)


def get_python_version():
    return sys.version_info


def is_macos():
    return platform.system() == "Darwin"


def is_linux():
    return platform.system() == "Linux"


def has_brew():
    return run("which brew", check=False, capture=True).returncode == 0


def brew_install(packages):
    """Install packages via Homebrew."""
    print(f"[macOS] Installing system packages: {', '.join(packages)}")
    run(f"brew install {' '.join(packages)}")


def apt_install(packages):
    """Install packages via apt."""
    print(f"[Linux] Installing system packages: {', '.join(packages)}")
    run(f"sudo apt-get update && sudo apt-get install -y {' '.join(packages)}")


def install_system_deps():
    """Install OS-level dependencies required by Python packages."""
    if is_macos():
        if not has_brew():
            print("[ERROR] Homebrew not found. Please install it first:")
            print("        /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"")
            sys.exit(1)

        # Check which packages are already installed
        needed = []
        for pkg in ["libomp", "pango"]:
            result = run(f"brew list {pkg} >/dev/null 2>&1", check=False, capture=True)
            if result.returncode != 0:
                needed.append(pkg)

        if needed:
            brew_install(needed)
        else:
            print("[macOS] System packages already installed: libomp, pango")

        # Add libomp to shell profile if not present
        add_libomp_to_profile()

    elif is_linux():
        needed = ["libgomp1", "libpango-1.0-0", "libpangoft2-1.0-0"]
        print(f"[Linux] Ensure these packages are installed: {', '.join(needed)}")
        print("        Run: sudo apt-get install -y " + " ".join(needed))
    else:
        print(f"[WARNING] Unsupported OS: {platform.system()}. Manual dependency installation may be needed.")


def add_libomp_to_profile():
    """Ensure DYLD_LIBRARY_PATH includes libomp for macOS."""
    libomp_path = "/usr/local/opt/libomp/lib"
    if not os.path.exists(libomp_path):
        # Try homebrew prefix detection
        result = run("brew --prefix libomp", check=False, capture=True)
        if result.returncode == 0:
            libomp_path = os.path.join(result.stdout.strip(), "lib")
        else:
            return

    export_line = f'export DYLD_LIBRARY_PATH="{libomp_path}:$DYLD_LIBRARY_PATH"'

    for profile in ["~/.zshrc", "~/.bash_profile", "~/.bashrc"]:
        path = os.path.expanduser(profile)
        if os.path.exists(path):
            with open(path, "r") as f:
                content = f.read()
            if "libomp" in content:
                print(f"[macOS] libomp already in {profile}")
                return

    # Add to the first available profile
    for profile in ["~/.zshrc", "~/.bash_profile", "~/.bashrc"]:
        path = os.path.expanduser(profile)
        if os.path.exists(path):
            with open(path, "a") as f:
                f.write(f"\n# Added by Insights installer for xgboost/lightgbm\n{export_line}\n")
            print(f"[macOS] Added libomp path to {profile}")
            print(f"        Run: source {profile}")
            return


def install_python_deps(group="all"):
    """Install Python dependencies."""
    py_major, py_minor = get_python_version()[:2]
    print(f"[Python] Version: {py_major}.{py_minor}")

    # Base command
    pip = sys.executable.replace("python", "pip")
    extras = {
        "ml": "ml",
        "nlp": "nlp",
        "vectordb": "vectordb",
        "export": "export",
        "all": "all",
    }.get(group, "all")

    # Install core + selected extras via pyproject.toml
    print(f"[pip] Installing insights[{extras}] ...")
    run(f'{pip} install -e ".[{extras}]"')

    # Handle Python 3.14+ onnxruntime incompatibility for chromadb
    if py_major >= 3 and py_minor >= 14 and (group in ("all", "vectordb")):
        print("[Python 3.14+] onnxruntime has no wheels for Python 3.14 yet.")
        print("[Python 3.14+] Installing chromadb without onnxruntime + manual deps ...")
        run(f'{pip} install chromadb --no-deps')
        # Install chromadb's other deps except onnxruntime
        chromadb_deps = [
            "build>=1.0.3",
            "chroma-hnswlib",
            "fastapi>=0.95.2",
            "grpcio>=1.58.0",
            "jsonschema>=4.19.0",
            "kubernetes>=28.1.0",
            "mmh3>=4.0.1",
            "numpy>=1.22.5",
            "opentelemetry-api>=1.2.0",
            "opentelemetry-exporter-otlp-proto-grpc>=1.2.0",
            "opentelemetry-sdk>=1.2.0",
            "orjson>=3.9.12",
            "overrides>=7.3.1",
            "posthog>=2.4.0",
            "pydantic>=1.9",
            "pydantic-settings>=2.0",
            "pybase64>=1.4.1",
            "pypika>=0.48.9",
            "python-dotenv>=1.0.1",
            "rich>=10.11.0",
            "tenacity>=8.2.3",
            "tokenizers>=0.13.2",
            "tqdm>=4.65.0",
            "typer>=0.9.0",
            "typing_extensions>=4.5.0",
            "uvicorn[standard]>=0.18.3",
            "uvloop>=0.19.0",
        ]
        run(f'{pip} install "{" "}".join(chromadb_deps)"')
        print("[Python 3.14+] chromadb installed. Use a custom embedding provider (e.g. OpenAI, sentence-transformers).")


def verify_imports():
    """Verify that all key packages can be imported."""
    print("\n[Verify] Checking imports ...")
    os.environ["DYLD_LIBRARY_PATH"] = "/usr/local/opt/libomp/lib:" + os.environ.get("DYLD_LIBRARY_PATH", "")

    packages = {
        "sklearn": "scikit-learn",
        "xgboost": "xgboost",
        "lightgbm": "lightgbm",
        "prophet": "prophet",
        "transformers": "transformers",
        "spacy": "spacy",
        "langchain": "langchain",
        "faiss": "faiss-cpu",
        "elasticsearch": "elasticsearch",
        "chromadb": "chromadb",
        "plotly": "plotly",
        "weasyprint": "weasyprint",
        "pptx": "python-pptx",
        "reportlab": "reportlab",
    }

    all_ok = True
    for module, pkg in packages.items():
        try:
            __import__(module)
            print(f"  {pkg}: OK")
        except Exception as e:
            all_ok = False
            print(f"  {pkg}: FAIL ({e})")

    if all_ok:
        print("\n[Verify] All packages import successfully.")
    else:
        print("\n[Verify] Some packages failed to import. Check errors above.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Install Insights optional dependencies")
    parser.add_argument("--group", choices=["ml", "nlp", "vectordb", "export", "all"], default="all",
                        help="Which dependency group to install (default: all)")
    parser.add_argument("--verify", action="store_true", help="Only verify existing imports")
    args = parser.parse_args()

    if args.verify:
        verify_imports()
        return

    print("=" * 60)
    print("Insights Dependency Installer")
    print("=" * 60)

    install_system_deps()
    install_python_deps(group=args.group)
    verify_imports()

    print("\n" + "=" * 60)
    print("Installation complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
