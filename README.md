# Connect

Prosty czat peer-to-peer TCP. Program działa na obu urządzeniach: każdy węzeł
nasłuchuje połączeń, a jeden z nich dodatkowo inicjuje połączenie z adresem IP
drugiego.

Wymagany jest Python 3. Utwórz środowisko wirtualne i zainstaluj zależności:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
```

`requirements.txt` nie zawiera obecnie zewnętrznych pakietów — program
korzysta wyłącznie z biblioteki standardowej Pythona. Środowisko `.venv` jest
lokalne i nie należy go kopiować ani commitować; na drugim urządzeniu utwórz je
osobno tymi samymi poleceniami.

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
