# Git — ściągawka

## Codzienny flow

```bash
# 1. Zastejdżuj pliki
git add nazwa_pliku.py
git add .                  # wszystkie zmienione pliki

# 2. Commit
git commit -m "Opis zmiany"

# 3. Push
git push

  Teraz w terminalu:

  git add version.py server/app_version.json extension/manifest.json GIT.md
  git commit -m "Bump version to 1.2.0"
  git push
  git tag v1.2.0
  git push origin v1.2.0
```

## Przydatne komendy

```bash
git status                 # co jest zmienione / zastejdżowane
git diff                   # co się zmieniło (niezastejdżowane)
git diff --staged          # co jest w stagu (pójdzie do commita)
git log --oneline -10      # ostatnie 10 commitów
git pull                   # pobierz zmiany z GitHuba
```

## Cofanie zmian

```bash
git restore nazwa_pliku    # cofnij zmiany w pliku (przed stagiem)
git restore --staged plik  # usuń plik ze stagu (nie kasuje zmian)
git revert HEAD            # cofnij ostatni commit (bezpieczne)
```

## Branche

```bash
git checkout -b nazwa      # nowy branch
git checkout main          # wróć do main
git merge nazwa            # scal branch do aktualnego
```
