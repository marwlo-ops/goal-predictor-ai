# API-Football — bezpieczne połączenie z GitHub Pages

## 1. Utwórz klucz API

1. Wejdź na https://dashboard.api-football.com/ i zaloguj się lub załóż konto.
2. W panelu przejdź do **Account → My Access** (nazwy mogą się nieznacznie zmieniać).
3. Skopiuj API key. Nie wysyłaj go w czacie i nie wklejaj do plików strony.
4. Darmowy plan jest limitowany liczbą zapytań dziennie; sprawdź aktualne limity na stronie planów.

Oficjalny poradnik: https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide

## 2. Dlaczego potrzebny jest pośrednik?

GitHub Pages publikuje pliki statyczne. Klucz umieszczony w JavaScript byłby widoczny dla każdego odwiedzającego. Dlatego plik `cloudflare-worker/worker.js` działa jako proxy, a klucz przechowywany jest jako sekret Cloudflare Worker.

## 3. Wdróż Cloudflare Worker

1. Zaloguj się do https://dash.cloudflare.com/ i otwórz **Workers & Pages**.
2. Utwórz Worker, np. `goal-predictor-api`.
3. Wklej zawartość pliku `cloudflare-worker/worker.js), zapisz i wdroż.
4. W ustawieniach Workera dodaj secret:
   - `API_FOOTBALL_KEY` = Twój klucz API-Football.
5. Dodaj zmienną tekstową:
   - `ALLOWED_ORIGIN` = dokładny origin strony GitHub Pages, np. `https://NAZWA-UZYTKOWNIKA.github.io`. Jeśli projekt jest publikowany pod ścieżką repozytorium, origin nadal nie zawiera ścieżki.
6. Zapisz zmiany i skopiuj adres Workera.

Worker udostępnia tylko dozwolone endpointy i parametry, sprawdza origin, nie ujawnia klucza i buforuje odpowiedzi. Kontrola Origin/CORS nie jest pełną autoryzacją — publiczne proxy nadal może być wywoływane przez klienty spoza przeglądarki. Dla publicznego wdrożenia dodaj Cloudflare rate limiting/Turnstile lub inny limit nadużyć.

## 4. Podłącz klienta do strony

Plik `api-football-client.js` zawiera klienta do endpointów proxy. Po wdrożeniu Workera ustaw przed jego załadowaniem:

```html
<script>window.GPA_API_BASE_URL = "https://TWOJ-WORKER.workers.dev";</script>
<script src="./api-football-client.js"></script>
```

Nie wpisuj tutaj klucza API — tylko publiczny adres Workera. Funkcje klienta są dostępne przez `GoalPredictorApiFootball`, np.:

```js
const data = await GoalPredictorApiFootball.headToHead(33, 34, { last: 10 });
```

Parametry `teamA` i `teamB` to identyfikatory drużyn API-Football, nie ich nazwy. Integracja interfejsu musi przekazywać ID drużyn i fixture z danych API.

## 5. Dostępne endpointy

- `/api/fixtures?date=YYYY-MM-DD`
- `/api/h2h?h2h=ID_DRUZYNY_A-ID_DRUZYNY_B&last=10`
- `/api/statistics?fixture=ID_MECZU`
- `/api/team-statistics?league=ID_LIGI&season=2026&team=ID_DRUZYNY`
- `/api/standings?league=ID_LIGI&season=2026`
- `/api/injuries?league=ID_LIGI&season=2026`
- `/api/odds?fixture=ID_MECZU`

Zakres danych i sezonów zależy od dostępności w planie API-Football. Statystyki historyczne kart, rożnych i strzałów mogą nie istnieć dla każdego spotkania.

## Uwaga

Ten commit dodaje bezpieczny szkielet proxy i klienta. Worker trzeba wdrożyć w koncie Cloudflare i skonfigurować, a klienta należy włączyć w interfejsie strony po ustaleniu identyfikatorów meczów i drużyn. Sama zmiana w repozytorium nie uruchamia zewnętrznego Workera automatycznie.
