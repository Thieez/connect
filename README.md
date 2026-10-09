# Connect

Prosty czat peer-to-peer TCP. Program działa na obu urządzeniach: każdy węzeł
nasłuchuje połączeń, a jeden z nich dodatkowo inicjuje połączenie z adresem IP
drugiego.

Wymagany jest Python 3. Utwórz środowisko wirtualne i zainstaluj zależności:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
```

Zależności obejmują serwer relay oraz klienta WebSocket. Środowisko `.venv`
jest lokalne i nie należy go kopiować ani commitować; na drugim urządzeniu
utwórz je osobno tymi samymi poleceniami.

## Uruchomienie

Na pierwszym urządzeniu uruchom nasłuchiwanie:

```powershell
.\.venv\Scripts\python.exe .\connect.py
```

Na drugim urządzeniu podaj aktualny adres IP pierwszego:

```powershell
.\.venv\Scripts\python.exe .\connect.py --connect 192.168.1.20
```

Oba węzły używają domyślnie portu TCP `8765`. W razie potrzeby ustaw ten sam
port po obu stronach przez `--port`, np.
`.\.venv\Scripts\python.exe .\connect.py --port 9000`.
Wpisz wiadomość i naciśnij Enter; `/quit` kończy działanie programu.

Urządzenia muszą mieć wzajemną łączność sieciową, a zapora musi zezwalać na
połączenia przychodzące TCP na używanym porcie. Połączenie przez Internet może
wymagać przekierowania portu TCP na routerze. Program nie zapewnia
automatycznego przechodzenia przez NAT, szyfrowania ani uwierzytelniania;
używaj go tylko w zaufanej sieci.

## Relay dla różnych sieci i CGNAT

Serwer relay przekazuje wiadomości pomiędzy dwoma klientami, więc nie wymaga
bezpośredniego połączenia urządzeń. W repozytorium jest `render.yaml` dla
Render.com. Utwórz na Render nową usługę typu **Blueprint** wskazującą to
repozytorium i wdroż ją; po wdrożeniu skopiuj adres usługi, np.
`https://connect-relay.onrender.com`. Endpoint `/` zwraca status działania.

Na obu urządzeniach wygeneruj ten sam trudny do odgadnięcia kod pokoju
(możesz wygenerować go tylko raz i przekazać drugiej osobie):

```powershell
py -3 -c "import secrets; print(secrets.token_urlsafe(16))"
```

Uruchom klienta na obu urządzeniach, podając adres wdrożonego serwera oraz ten
sam kod pokoju:

```powershell
.\.venv\Scripts\python.exe .\connect.py --relay https://connect-relay.onrender.com --room WKLEJ_TUTAJ_KOD
```

Po połączeniu obu klientów można pisać wiadomości; `/quit` rozłącza klienta.
Bezpłatna usługa Render może usypiać się po okresie bezczynności, więc pierwsze
połączenie po przerwie może chwilę potrwać.

Kod pokoju działa jak hasło dostępu: każdy, kto go zna, może dołączyć do
pokoju. Relay nie zapisuje historii, ale przekazuje wiadomości jako zwykły
tekst wewnątrz połączenia TLS (`https`/`wss`); operator serwera może mieć do
nich dostęp. Nie przesyłaj poufnych danych.
