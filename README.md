# Virtual Environment Setup Guide

## Prerequisites

- **Python 3.12** installed on your system
  - Download from [python.org](https://www.python.org/downloads/)
  - Make sure to check "Add Python to PATH" during installation

## Setting Up Virtual Environment

### Step 1: Create Virtual Environment

Navigate to your project directory and run:

```bash
py -3.12 -m venv venv
```

This creates a folder called `venv` with an isolated Python environment.

### Step 2: Activate Virtual Environment

**Windows Command Prompt:**
```cmd
venv\Scripts\activate
```

**Windows PowerShell:**
```powershell
venv\Scripts\Activate.ps1
```

**Git Bash / Linux / macOS:**
```bash
source venv/bin/activate
```

After activation, you should see `(venv)` at the beginning of your command line.

### Step 3: Install Dependencies

With the virtual environment activated:

```bash
pip install -r requirements.txt
```

## Using the Virtual Environment

### Running Python Scripts

**Option 1 - With activated virtual environment:**
```bash
# First activate
venv\Scripts\activate

# Then run
python your_script.py
```

**Option 2 - Direct path (without activation):**
```bash
venv\Scripts\python.exe your_script.py
```

### Installing New Packages

Always activate the virtual environment first, then:

```bash
pip install package-name
```

To save new dependencies:
```bash
pip freeze > requirements.txt
```

### Checking Installed Packages

```bash
pip list
```

### Deactivating Virtual Environment

When you're done working:

```bash
deactivate
```

## Quick Reference

| Command | Description |
|---------|-------------|
| `py -3.12 -m venv venv` | Create virtual environment |
| `venv\Scripts\activate` | Activate (Windows CMD) |
| `venv\Scripts\Activate.ps1` | Activate (PowerShell) |
| `source venv/bin/activate` | Activate (Linux/Mac) |
| `pip install -r requirements.txt` | Install all dependencies |
| `pip install package-name` | Install single package |
| `pip list` | List installed packages |
| `deactivate` | Deactivate virtual environment |

## Troubleshooting

### Python 3.12 not found

If you get an error when creating the venv, try:
```bash
python -m venv venv
```

Or verify your Python version:
```bash
python --version
```

### PowerShell execution policy error

If you can't run the activation script in PowerShell, run this once as Administrator:
```powershell
Set-ExecutionPolicy RemoteSigned
```

### pip not recognized

Use:
```bash
python -m pip install -r requirements.txt
```

## Why Use a Virtual Environment?

- **Isolation**: Each project has its own dependencies
- **No conflicts**: Different projects can use different package versions
- **Clean system**: Keeps your system Python clean
- **Reproducibility**: Easy to recreate the environment on another machine

## Notes

- The `venv` folder should **NOT** be committed to git
- Always activate the virtual environment before working on the project
- Use Python 3.12 for best compatibility (Python 3.14 has package compatibility issues)
