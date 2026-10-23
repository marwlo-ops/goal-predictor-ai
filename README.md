# Goal Predictor AI ⚽

Mobilna aplikacja PWA do analizy meczów piłkarskich. Projekt jest przygotowany do wrzucenia do repozytorium GitHub.

## Funkcje
- Responsywny interfejs w języku polskim.
- Instalacja na ekranie głównym telefonu (PWA).
- Model Poissona dla 1X2, over 1.5, over 2.5 i BTTS.
- Zaplanowany workflow GitHub Actions, który publikuje dane o 13:00 czasu `Europe/Warsaw`.
- Filtr spotkań z kickoffem między 15:00 a 22:00 czasu polskiego.
- Opcjonalny komentarz AI przez OpenAI API.
- Bez udawania aktualnych danych: bez tokena API lista pozostaje pusta.

## Ważne o źródłach
Ten projekt używa `football-data.org` jako integracji startowej, ponieważ udostępnia dokumentowane API. Nie korzysta z nieoficjalnego scrapingu SofaScore/Flashscore. Nie mam podstaw, by zagwarantować publiczny, oficjalny i bezpłatny API tych serwisów. Jeśli masz legalny klucz/licencję do danych SofaScore lub Flashscore, integrację można dopisać jako osobny adapter zgodny z ich warunkami.

Dostępny zakres lig, historii i statystyk zależy od planu API. Prototyp wylicza estymowane gole z ostatnich wyników; nie nazywa ich oficjalnym xG. Składy, kontuzje, kursy, rożne i kartki nie są jeszcze dostępne w tej wersji.

## Integracja Sportmonks (Football API v3)

Projekt pobiera dodatkowy terminarz ze Sportmonks i scala go z `data/latest.json`; osobny plik `data/sportmonks.json` zachowuje dane źródłowe i diagnostykę. Synchronizacja jest zaplanowana co 30 minut przez GitHub Actions. Spotkania znalezione wyłącznie w Sportmonks są dodawane jako `fixture_only` bez zmyślonych prawdopodobieństw. Dostęp do statystyk, kursów, predykcji i lig zależy od uprawnień tokena oraz wybranego planu.

W repozytorium otwórz **Settings → Secrets and variables → Actions**. Na zrzucie ekranu sekret został nazwany `NEWAPT`; workflow odczytuje go jako `SPORTMONKS_API_TOKEN` przez mapowanie `secrets.NEWAPT`. Jeśli sekret ma inną nazwę, zmień mapowanie w `.github/workflows/sportmonks.yml` albo nazwij sekret `NEWAPT`. Nigdy nie umieszczaj wartości tokena w plikach strony ani w commitach.

Test integracji: **Actions → Sportmonks Football Data → Run workflow**. Sprawdź logi, a potem pliki `data/sportmonks.json` i `data/latest.json`. Błąd 401 zwykle oznacza zły/brakujący token; 403 — brak uprawnień planu; 429 — limit zapytań. Nieudane zapytania do poszczególnych dat są zapisywane w diagnostyce, a całkowita awaria źródła nie powinna zastąpić feedu pustymi danymi.

## Publikacja na GitHubie

1. Utwórz nowe repozytorium na https://github.com/new (np. `goal-predictor-ai`).
2. Rozpakuj ZIP i wgraj całą zawartość do repozytorium, zachowując katalog `.github`.
3. W GitHub otwórz **Settings → Secrets and variables → Actions → New repository secret**.
4. Dodaj `FOOTBALL_DATA_TOKEN` — token z konta https://www.football-data.org/client/register.
5. Opcjonalnie dodaj `OPENAI_API_KEY`, jeśli chcesz, by AI pisało zwięzłe podsumowania. Użycie API OpenAI jest rozliczane oddzielnie; samo posiadanie ChatGPT nie zapewnia klucza API.
6. Otwórz **Settings → Actions → General** i upewnij się, że workflow może zapisywać do repozytorium (workflow ma `contents: write`).
7. Otwórz **Actions → Publish daily football predictions → Run workflow**, by uruchomić ręcznie test.
8. Włącz GitHub Pages: **Settings → Pages → Deploy from a branch → `main` → `/ (root)` → Save**. Po chwili strona będzie dostępna pod adresem podanym przez GitHub.

## Jak działa harmonogram
Workflow sprawdza godzinę co godzinę i uruchamia publikację tylko w oknie 13:00–13:24 czasu `Europe/Warsaw`. Ręczne uruchomienie z Actions omija kontrolę godziny. GitHub Actions może opóźniać zaplanowane zadania, więc nie jest to gwarancja co do sekundy.

## Jak działają prognozy
Model Poissona przelicza rozkłady liczby goli na 1X2, over 1.5, over 2.5 i BTTS. Parametry goli są estymowane z ostatnich dostępnych wyników drużyn i uproszczonej korekty gospodarzy. To wersja bazowa do walidacji, nie sprawdzony model przewagi nad rynkiem. Należy prowadzić historię prognoz i mierzyć kalibrację, ROI oraz wyniki względem kursów zamknięcia przed wyciąganiem wniosków.

## Prywatność i bezpieczeństwo
Nigdy nie wpisuj tokenów API w `index.html` ani nie commituj ich w kodzie. Używaj GitHub Secrets. W przypadku publicznego repozytorium wyniki prognoz w `data/latest.json` są publiczne.
