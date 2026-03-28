# Wymagany: webextension-polyfill

Pobierz plik `browser-polyfill.js` z oficjalnego repozytorium Mozilla:

    https://github.com/mozilla/webextension-polyfill/releases/latest

Pobierz plik `browser-polyfill.min.js` i zapisz jako:

    extension/lib/browser-polyfill.js

Ten plik normalizuje API przeglądarek (Chrome callbacks → Promise-based `browser.*`)
i umożliwia działanie rozszerzenia na Chrome, Firefox i Edge z jednego kodu.

Instalacja przez npm (alternatywnie):

    npm install webextension-polyfill
    cp node_modules/webextension-polyfill/dist/browser-polyfill.min.js extension/lib/browser-polyfill.js
