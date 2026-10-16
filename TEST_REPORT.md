# PROSTE WIDEO — raport testów

**Środowisko:** Linux, Python 3, OpenCV, NumPy, Pillow, Tkinter, FFmpeg; testy GUI w wirtualnym ekranie Xvfb.

**Wyniki pozytywne:**

- 8/8 testów `pytest` (`test_core.py`, `test_new_features.py`).
- Poprawność rozmywania, pikselizacji, zachowania obrazu poza maską owalną, regulacja szerokości i wysokości owalu.
- Korelacja fazowa i dopasowanie kontrastowe na syntetycznym ruchu; ręczne klatki kluczowe; cięcie i zmiana kolejności fragmentów.
- Eksport wideo H.264 wraz z dźwiękiem po zmianie kolejności fragmentów.
- `tests/gui_full_smoke.py` — pełny dotychczasowy scenariusz GUI: wczytaj, śledź, klatka kluczowa, cięcie, przestawienie, zapis/odczyt projektu, eksport z dźwiękiem.
- `tests/gui_new_features.py` — wczytanie filmu, ustawienie maski owalnej i suwaków, cięcie `B`, odtwarzanie `Spacja`, przeciąganie kafelków, zapis i odczyt owalu i segmentów, eksport z dźwiękiem.
- Wykonano wizualną inspekcję układu aplikacji w oknie 1440×900.

**Niezweryfikowane w tym środowisku:** natywne budowanie i uruchamianie `PROSTE_WIDEO.exe` na Windows, zachowanie UI na wszystkich skalowaniach DPI i rozdzielczościach, pliki wideo ze zmienną liczbą klatek na sekundę, przypadki wszystkich kodeków, zachowanie klatek dokładnie na granicach cięć dla wszystkich źródeł.

**Dostawa:** kod źródłowy, testy oraz skrypty budowania EXE; **nie** gotowy prekompilowany EXE.
