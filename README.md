# Connect

Prosty czat peer-to-peer TCP. Program działa na obu urządzeniach: każdy węzeł
nasłuchuje połączeń, a jeden z nich dodatkowo inicjuje połączenie z adresem IP
drugiego.

Wymagany jest Python 3; nie trzeba instalować dodatkowych pakietów.

## Uruchomienie

Na pierwszym urządzeniu uruchom nasłuchiwanie:

```powershell
python connect.py
```

Na drugim urządzeniu podaj aktualny adres IP pierwszego:

```powershell
python connect.py --connect 192.168.1.20
```

Oba węzły używają domyślnie portu TCP `8765`. W razie potrzeby ustaw ten sam
port po obu stronach przez `--port`, np. `python connect.py --port 9000`.
Wpisz wiadomość i naciśnij Enter; `/quit` kończy działanie programu.

Urządzenia muszą mieć wzajemną łączność sieciową, a zapora musi zezwalać na
połączenia przychodzące TCP na używanym porcie. Połączenie przez Internet może
wymagać przekierowania portu TCP na routerze. Program nie zapewnia
automatycznego przechodzenia przez NAT, szyfrowania ani uwierzytelniania;
używaj go tylko w zaufanej sieci.
