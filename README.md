# Goal Predictor AI — Football Intelligence ⚽

Nowa oprawa wizualna: neonowy granat, elektryczny błękit, turkus i fiolet; odświeżone logo SVG, responsywny interfejs i aktualizacja cache PWA. Aplikacja nadal korzysta z istniejącego HTML/CSS/JavaScript — zmiana wyglądu nie wymaga przebudowy pipeline danych.

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

W repozytorium otwórz **Settings → Secrets and variables → Actions**. Dodaj sekret repozytorium o dokładnej nazwie `SPORTMONKS`; workflow przekazuje go do skryptu jako `SPORTMONKS_API_TOKEN`. Jeśli sekret ma inną nazwę, zmień mapowanie w `.github/workflows/sportmonks.yml`. Nigdy nie umieszczaj wartości tokena w plikach strony ani w commitach.

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
Workflow sprawdza się co godzinę, ale planową publikację uruchamia tylko w godzinie 13:00–13:59 czasu `Europe/Warsaw` (cron rozpoczyna kontrolę w 17. minucie każdej godziny). Ręczne uruchomienie z Actions omija kontrolę godziny. GitHub Actions może opóźniać zaplanowane zadania, więc nie jest to gwarancja co do sekundy.

## Jak działają prognozy
Model Poissona przelicza rozkłady liczby goli na 1X2, over 1.5, over 2.5 i BTTS. Parametry goli są estymowane z ostatnich dostępnych wyników drużyn i uproszczonej korekty gospodarzy. To wersja bazowa do walidacji, nie sprawdzony model przewagi nad rynkiem. Należy prowadzić historię prognoz i mierzyć kalibrację, ROI oraz wyniki względem kursów zamknięcia przed wyciąganiem wniosków.

## Prywatność i bezpieczeństwo
Nigdy nie wpisuj tokenów API w `index.html` ani nie commituj ich w kodzie. Używaj GitHub Secrets. W przypadku publicznego repozytorium wyniki prognoz w `data/latest.json` są publiczne.


## Unified data pipeline
The hourly workflow checks whether a publication is needed, but the scheduled forecast publication is restricted to the 13:00 hour in `Europe/Warsaw`; manual workflow runs bypass the time gate. It generates model-backed fixtures from football-data.org and invokes `scripts/sync_data_sources.py` to synchronize Sportmonks and API-Football when their secrets are available. Sportmonks is skipped by the shared pipeline when its feed was refreshed in the previous 25 minutes, avoiding duplicate calls with the dedicated 30-minute workflow. Optional-provider failures are reported without discarding valid base predictions. Fixtures without reliable probabilities remain in provider feeds rather than becoming prediction cards. Homepage counters and league tabs count only model-backed matches; unsupported source-only fixtures are reported separately. Probability parsing detects whether the 1X2 total is expressed as percentages or fractions, and the Poisson model uses a wider score matrix with a common normalization factor. The publish workflow also runs model unit tests and checks embedded JavaScript syntax before updating data.

## Zaawansowany model analityczny i walidacja

- Prognozy mają dodatkowe wyliczenia z rozkładu Dixon–Coles oraz powtarzalną symulację Monte Carlo. W odpowiedzi zachowane są dotychczasowe klucze rynków 1X2, over 1.5, over 2.5 i BTTS, a także gole drużyn i over 3.5.
- Plik \`data/prediction-history.json\` zachowuje pierwszą opublikowaną prognozę przed rozpoczęciem spotkania; kolejne uruchomienia nie nadpisują tego pierwszego przewidywania. Archiwum jest ograniczane do około roku i maksymalnie 12 000 rekordów.
- \`data/results.json\` gromadzi wyniki końcowe z codziennych pobrań, zamiast kasować starsze rekordy po siedmiu dniach. \`scripts/evaluate_predictions.py\` porównuje archiwum z wynikami i zapisuje \`data/model-performance.json\` z liczbą rozstrzygniętych spotkań, skutecznością, Brier Score i log loss dla dostępnych rynków.
- Interfejs pokazuje raport skuteczności dopiero wtedy, gdy plik raportu jest dostępny. Nie ma danych treningowych do automatycznego dopasowania parametru rho w tej wersji; parametr Dixon–Coles ma wartość domyślną i jest jawnie oznaczony jako niedopasowany do konkretnej ligi.
- Monte Carlo symuluje wyniki z tego samego rozkładu modelu. To sprawdzenie rozkładu i niepewności numerycznej, a nie niezależna prognoza ani gwarancja trafienia.
- Testy uruchamia się poleceniem \`python -m unittest discover -s tests -v\`.
