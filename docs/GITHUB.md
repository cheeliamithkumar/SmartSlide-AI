# GitHub Setup

The repository is already initialised with logical commits on the `main` branch. `.env` files, virtual
environments, `node_modules`, build output and runtime storage are ignored.

## Push to a new GitHub repository

1. Create an **empty** repository on GitHub (no README, .gitignore or license), e.g. `SmartSlide-AI`.
2. From the project folder:

```bash
git remote add origin https://github.com/<your-username>/SmartSlide-AI.git
```

```bash
git push -u origin main
```

GitHub requires a **Personal Access Token** (not your password) for HTTPS pushes, or an SSH key:

- **HTTPS:** create a fine-grained token at GitHub → Settings → Developer settings → Personal access tokens, with
  *Contents: Read and write* on the repository, and use it as the password when Git asks. Alternatively,
  run `gh auth login` with the GitHub CLI.
- **SSH:** add your public key at GitHub → Settings → SSH and GPG keys, then use
  `git remote add origin git@github.com:<your-username>/SmartSlide-AI.git`.

## Before every commit

```bash
git status
```

Make sure no `.env` file or secrets appear in the staged changes. Only `.env.example` files belong in Git.

## Optional: CI

A GitHub Actions workflow that runs the backend tests and frontend build lives at `.github/workflows/ci.yml`.
