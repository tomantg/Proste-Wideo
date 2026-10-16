# PROSTE WIDEO — edytor wideo dla Windows

Ciemny, minimalistyczny edytor wideo: maskowanie prostokątne i owalne, regulacja intensywności rozmycia/pikselizacji, automatyczne śledzenie, klatki kluczowe, cięcie i przestawianie fragmentów na osi czasu, eksport MP4/H.264 z dźwiękiem.

## Co nowego

- Nazwa programu: **PROSTE WIDEO**, bez żółtych elementów i zbędnych opisów.
- Kafelkowa oś czasu z miniaturami fragmentów. Kliknij kafelek, aby ustawić głowicę, przeciągnij na inny, aby zmienić kolejność; użyj przycisków `Przesuń` lub `Usuń`, jeżeli wolisz.
- **B**: podział bieżącego fragmentu w miejscu głowicy; **Spacja**: odtwarzanie/pauza (o ile kursor nie jest w polu tekstowym).
- **Ellipse**: maska owalna; po jej wybraniu reguluj kształt dwoma suwakami szerokości i wysokości, a cały prostokąt ograniczający przeciągnij lub zmień jego rozmiar uchwytami w podglądzie. Można używać rozmycia Gaussian lub Mosaic; maska ma łagodną krawędź.
- Ręczne poprawki maski w klatkach kluczowych; tracking kontrastowy/korelacja fazowa; zapis/odczyt projektu; eksport H.264/AAC z zachowaniem lub przestawieniem audio zgodnie z kolejnością kafelków.

## Budowanie EXE na Windows 10/11 (x64)

1. Zainstaluj **Python 3.12 (64-bit)** z python.org (zaznacz `Add Python to PATH`).
2. Rozpakuj wszystkie pliki, zachowując strukturę folderów.
3. Kliknij dwukrotnie `build_windows.bat`. Wymagane jest połączenie z internetem przy pierwszym budowaniu.
4. Jeśli testy i kompilacja się powiodą, program pojawi się jako **`dist\PROSTE_WIDEO.exe`**.
5. Na kolejnym uruchomieniu otwórz `.exe` bez Pythona lub użyj `run_windows.bat`.

Archiwum **nie zawiera skompilowanego pliku EXE**. Skrypty budują go natywnie na Windows. Możliwe są ostrzeżenia SmartScreen dla aplikacji bez podpisu cyfrowego.

## GitHub Actions — z komputera Mac

1. Utwórz lub otwórz repozytorium na GitHubie.
2. Prześlij **zawartość** folderu `PROSTE_WIDEO_Windows` do głównego katalogu repozytorium — koniecznie `proste_wideo.py`, `proste_wideo_core.py`, `tests/`, `requirements.txt` i ukryty `.github/workflows/windows-build.yml`.
3. Jeśli repozytorium zawiera starsze pliki `protovid.py` / `protovid_core.py`, można je usunąć po przeniesieniu projektu (nowa kompilacja z nich nie korzysta).
4. W zakładce **Actions → PROSTE WIDEO Windows EXE → Run workflow** uruchom budowanie (albo poczekaj na uruchomienie przy `push`).
5. Po udanym wykonaniu pobierz artefakt **PROSTE-WIDEO-Windows-exe**. Po rozpakowaniu znajdziesz `PROSTE_WIDEO.exe`.

Jeżeli po wgraniu plików nie widzisz workflow, sprawdź jego pełną ścieżkę `.github/workflows/windows-build.yml` na gałęzi `main` lub `master` oraz czy GitHub Actions są włączone.

## Dodatkowe wskazówki

- Wideo na podglądzie jest odtwarzane z pliku źródłowego. Kafelki definiują **kolejność eksportu**. Po kliknięciu w kafelek przeskakujesz do odpowiadającego mu fragmentu źródła.
- Maska owalna działa na rzeczywistym wyjściowym wideo, nie tylko na obrysie w podglądzie.
- W starych projektach `*.protovid.json` zachowana jest zgodność przy odczycie. Nowe projekty są zapisywane jako `*.prostewideo.json`.
- FFmpeg jest pobierany przez zależność `imageio-ffmpeg`. Większość typowych MP4/MOV/AVI/MKV powinna się odczytać, ale nie wszystkie możliwe kodeki czy materiały VFR są gwarantowane.
- Skrót `Ctrl+O` otwiera wideo, `Ctrl+S` zapisuje projekt.

## Testowanie

Silnik: `python -m pytest -q tests/test_core.py tests/test_new_features.py`. Testy GUI wymagają wyświetlacza. Informacje o zweryfikowanym zakresie znajdziesz w `TEST_REPORT.md`.
