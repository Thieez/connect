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
korzysta z publicznego STUN Google, aby wykryć publiczne adresy i spróbować
zestawić bezpośrednie połączenie. Biblioteka aiortc używana przez klienta
obsługuje jeden serwer STUN na próbę; można go zmienić zmienną
`CONNECT_STUN_SERVER`, np. `stun:stun.cloudflare.com:3478`. STUN nie przekazuje
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
Jeśli masz własny serwer TURN, możesz podać go bezpiecznie przez zmienne
środowiskowe zamiast umieszczać hasło w historii poleceń:

```powershell
$env:TURN_SERVER = "turn:turn.example.com:3478"
$env:TURN_USERNAME = "UZYTKOWNIK"
$env:TURN_PASSWORD = "HASLO"
```

Uruchom klienta z tymi samymi ustawieniami TURN na obu komputerach:

```powershell
.\.venv\Scripts\python.exe .\connect.py --p2p-relay https://connect-relay.onrender.com --room WKLEJ_TUTAJ_KOD --turn-server $env:TURN_SERVER --turn-username $env:TURN_USERNAME --turn-password $env:TURN_PASSWORD
```

Połączenie bezpośrednie nie jest gwarantowane: zależy od NAT, zapór i sieci.
Serwer Render pomaga peerom się odnaleźć i wymienić sygnalizację, ale nie może
wymusić bezpośredniej trasy przez restrykcyjny lub symetryczny CGNAT. W takim
przypadku skonfiguruj Cloudflare Realtime TURN: utwórz klucz TURN i token API
z uprawnieniem do generowania poświadczeń TURN. Ustaw na obu komputerach
zmienne środowiskowe (tokenu nie wklejaj do repozytorium):

```powershell
$env:CLOUDFLARE_TURN_KEY_ID = "ID_KLUCZA_TURN"
$env:CLOUDFLARE_TURN_API_TOKEN = "TOKEN_API"
```

Klient pobierze z Cloudflare tymczasowe poświadczenia ważne godzinę i użyje
ich przy negocjacji ICE. Szczegóły konfiguracji są w
[dokumentacji Cloudflare TURN](https://developers.cloudflare.com/realtime/turn/).
TURN może pomóc połączyć urządzenia zza restrykcyjnego CGNAT, ale przekazuje
ruch przez serwer TURN — to nie jest bezpośredni transfer między komputerami.
Cloudflare nalicza opłatę za transfer TURN, jeśli nie jest używany z ich SFU.
Bez TURN aplikacja po 45 sekundach przełącza wiadomości przez relay Render.

## Alternatywa: prywatna sieć WireGuard przez Headscale

Jeśli celem jest prywatne połączenie urządzeń, a niekoniecznie kanał WebRTC,
możesz uruchomić własny Headscale i użyć go jako control plane dla klienta
Tailscale. Nie wymaga to płatnego konta/control plane Tailscale, ale wymaga
własnego serwera. Instrukcja zawiera wariant Render (płatny Starter i trwały
dysk; Render nie zapewnia własnego UDP-STUN/DERP) oraz wariant VPS z własnym
UDP-STUN/DERP: [`headscale/README.md`](headscale/README.md).

Domyślnie klient używa Headscale `https://connect-headscale.onrender.com`,
dołącza Tailscale (jeśli to konieczne), pokazuje adres mesh i konfiguruje na
Windowsie reguły Zapory wymagane przez połączenie: port czatu TCP dostępny
tylko z podsieci `100.64.0.0/10`, domyślny port WireGuard UDP `41641`
przychodzący i wychodzący, STUN UDP `3478` wychodzący oraz HTTPS TCP `443`
wychodzący. Tailscale domyślnie najpierw próbuje zestawić trasę bezpośrednią
UDP pomiędzy peerami; jeśli NAT/CGNAT na to nie pozwala, automatycznie używa
zaszyfrowanego DERP. Klient wyłącza też opcję Tailscale „shields up”, która
blokowałaby połączenia przychodzące. Zapora nie może usunąć ograniczeń
narzuconych przez routera lub operatora. Jeśli połączenie nadal używa DERP,
sprawdź `tailscale netcheck` na obu komputerach. `UDP: true` jest wymagane,
ale samo nie gwarantuje bezpośredniej trasy. Jeśli router nie tworzy poprawnego
mapowania automatycznie, zarezerwuj lokalny adres IP komputera i przekieruj
na routerze UDP `41641` z Internetu do tego komputera; zrób to w sieci każdego
peera. Reguła zapory Windows utworzona przez klienta już zezwala na ten port.
Przekierowanie może pomóc, ale nie zadziała za CGNAT operatora ani przy
restrykcjach sieci blokujących UDP — w takich przypadkach DERP jest
oczekiwanym, szyfrowanym połączeniem awaryjnym. Dodaj `--no-headscale`, aby
wyłączyć automatyczne dołączenie do mesha.

Reguły zapory dla bezpośredniego Tailscale są tworzone automatycznie podczas
uruchamiania klienta Connect. Możesz je też skonfigurować i uruchomić
diagnostykę ręcznie na każdym komputerze z PowerShell uruchomionego jako
administrator:

```powershell
.\setup-tailscale-p2p.ps1
```

Skrypt otwiera w Zaporze Windows UDP `41641` i uruchamia `tailscale netcheck`.
Nie zmienia konfiguracji routera. Jeśli test nadal pokazuje trasę przez DERP,
zarezerwuj lokalny adres IP komputera i przekieruj UDP `41641` na routerze do
tego adresu. Konfigurację routera trzeba wykonać osobno dla każdej sieci;
przekierowanie nie zadziała za CGNAT ani przy blokadzie UDP.

Przy pierwszym uruchomieniu zaakceptuj monit UAC i wklej jednorazowy klucz,
gdy klient o niego poprosi. Na każdym urządzeniu użyj jego własnego klucza.
Reguły wymagają Windows PowerShell i uprawnień administratora; klient wyświetli
monit UAC. Reguły UDP otwierają wyłącznie porty używane przez Tailscale.

Przy starcie klient zapisuje bieżący wynik `tailscale netcheck` oraz stan tras
peerów co 15 sekund do `connect-mesh.log` i konsoli. Wpis `route=direct
endpoint=...` potwierdza bezpośrednią trasę; `route=DERP(...)` oznacza relay.
Serwer Headscale na Renderze zapisuje szczegółowe zdarzenia koordynacji w
Dashboard → `connect-headscale` → Logs. Te logi pokazują rejestrację i
aktualizacje mapy, ale sam Headscale nie widzi ścieżki pakietów WireGuard —
jej stan odczytuje się z `connect-mesh.log` po stronie klientów. Netcheck może
zawierać publiczny adres IP; zamazuj go przed udostępnieniem logu.

Na pierwszym komputerze uruchom serwer czatu (przy pierwszym uruchomieniu
wklej jego własny jednorazowy klucz Headscale):

```powershell
.\.venv\Scripts\python.exe .\connect.py --port 8765
```

Na drugim komputerze użyj jego własnego klucza przy pierwszym uruchomieniu
i podaj adres mesh pierwszego komputera:

```powershell
.\.venv\Scripts\python.exe .\connect.py --connect 100.x.y.z --port 8765
```

Klient nie może wymusić trasy bezpośredniej: `tailscale ping 100.x.y.z` pokaże
`direct`, jeśli NAT/firewalle na to pozwolą, albo `via DERP`, gdy połączenie
jest przekazywane. Obie trasy są szyfrowane WireGuard; domyślny tryb Headscale
dołącza klienta i konfiguruje potrzebne reguły Zapory Windows.
Restrukcyjny CGNAT może nadal wymagać relay.

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
