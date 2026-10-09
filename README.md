# Connect

Prosty czat peer-to-peer TCP. Program działa na obu urządzeniach: każdy węzeł
nasłuchuje połączeń, a jeden z nich dodatkowo inicjuje połączenie z adresem IP
drugiego.

Wymagany jest Python 3. Utwórz środowisko wirtualne i zainstaluj zależności:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
```

Zależności obejmują serwer relay, klienta WebSocket i WebRTC. Środowisko `.venv`
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
wymagać przekierowania portu TCP na routerze. Klasyczny tryb TCP (`--connect`)
nie zapewnia automatycznego przechodzenia przez NAT, szyfrowania ani
uwierzytelniania; używaj go tylko w zaufanej sieci.

## Bezpośrednie połączenie dla różnych sieci i CGNAT

Aby ograniczyć ruch przez serwer, oba urządzenia mogą użyć WebRTC. Serwer
sygnalizacyjny przekazuje tylko opis połączenia; po udanym ICE wiadomości
przesyłane są bezpośrednim, szyfrowanym kanałem danych. Program domyślnie
korzysta z publicznych serwerów STUN Google i Cloudflare, aby wykryć publiczne
adresy i spróbować zestawić bezpośrednie połączenie. Jeśli jeden z nich jest
blokowany, można ustawić własną listę rozdzieloną przecinkami w zmiennej
`CONNECT_STUN_SERVERS`, np. `stun:stun.example.net:3478`. STUN nie przekazuje
wiadomości. Po dołączeniu obu peerów klient pokazuje stany ICE/WebRTC; po 45
sekundach bez kanału danych automatycznie przełącza się na relay.

Na obu urządzeniach wygeneruj ten sam kod pokoju:

```powershell
py -3 -c "import secrets; print(secrets.token_urlsafe(16))"
```

Następnie uruchom klienta na obu urządzeniach z adresem serwera i wspólnym
kodem:

```powershell
.\.venv\Scripts\python.exe .\connect.py --p2p-relay https://connect-relay.onrender.com --room WKLEJ_TUTAJ_KOD
```

Jeśli bezpośrednie połączenie nie powiedzie się (np. przez restrykcyjny CGNAT),
program automatycznie przełączy wiadomości na relay przez ten sam serwer.
Można skonfigurować dodatkowy serwer TURN, aby ICE mógł spróbować połączenia
przez TURN przed przejściem na relay aplikacji:

```powershell
.\.venv\Scripts\python.exe .\connect.py --p2p-relay https://connect-relay.onrender.com --room WKLEJ_TUTAJ_KOD --turn-server turn:turn.example.com:3478 --turn-username UZYTKOWNIK --turn-password HASLO
```

Połączenie bezpośrednie nie jest gwarantowane: zależy od NAT, zapór i sieci.
Serwer Render pomaga peerom się odnaleźć i wymienić sygnalizację, ale nie może
wymusić bezpośredniej trasy przez restrykcyjny lub symetryczny CGNAT. W takim
przypadku może być potrzebny serwer TURN; TURN przekazuje ruch przez serwer
TURN, więc nie jest połączeniem bezpośrednim. Jeśli TURN nie jest
skonfigurowany, aplikacja przełącza wiadomości na relay przez Render.

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
sam kod pokoju. Ten tryb zawsze przekazuje wiadomości przez serwer; użyj
`--p2p-relay`, aby najpierw spróbować połączenia bezpośredniego.

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
