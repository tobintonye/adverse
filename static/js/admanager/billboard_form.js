(function () {
    const locationInput = document.getElementById('location-autocomplete');
    const dropdown      = document.getElementById('location-dropdown');
    const latInput      = document.getElementById('lat-input');
    const lngInput      = document.getElementById('lng-input');
    const coordsStatus  = document.getElementById('coords-status');

    if (latInput.value && lngInput.value) {
        coordsStatus.innerHTML = '<span class="text-white/100">📍 ' + parseFloat(latInput.value).toFixed(5) + ', ' + parseFloat(lngInput.value).toFixed(5) + '</span>';
        coordsStatus.classList.remove('hidden');
    }

    let debounceTimer;
    locationInput.addEventListener('input', function () {
        clearTimeout(debounceTimer);
        const q = locationInput.value.trim();
        if (q.length < 3) { hideDropdown(); return; }
        debounceTimer = setTimeout(function () { fetchSuggestions(q); }, 350);
    });

    function fetchSuggestions(query) {
        let finalQuery = query;
        const countrySelectEl = document.getElementById('country-input');
        const stateSelectEl   = document.getElementById('state-input');
        const countryVal = countrySelectEl ? countrySelectEl.value : '';
        const stateVal = stateSelectEl ? stateSelectEl.value : '';
        if (stateVal) finalQuery += ', ' + stateVal;
        if (countryVal) finalQuery += ', ' + countryVal;

        const url = 'https://nominatim.openstreetmap.org/search?q=' + encodeURIComponent(finalQuery) + '&format=json&limit=6&addressdetails=1';
        fetch(url, { headers: { 'Accept-Language': 'en', 'User-Agent': 'AdversApp/1.0' } })
            .then(res => res.json())
            .then(data => renderDropdown(data))
            .catch(() => hideDropdown());
    }

    function renderDropdown(results) {
        if (!results.length) { hideDropdown(); return; }
        dropdown.innerHTML = results.map(function (r) {
            const name = r.display_name.replace(/"/g, '&quot;');
            const country = r.address && r.address.country ? r.address.country.replace(/"/g, '&quot;') : '';
            const state = r.address && r.address.state ? r.address.state.replace(/"/g, '&quot;') : '';

            return '<button type="button"'
                + ' data-lat="' + r.lat + '"'
                + ' data-lon="' + r.lon + '"'
                + ' data-name="' + name + '"'
                + ' data-country="' + country + '"'
                + ' data-state="' + state + '"'
                + ' class="w-full text-left px-4 py-2.5 text-xs text-white/100 hover:bg-white/10 hover:text-white transition border-b border-white/5 last:border-0">'
                + r.display_name
                + '</button>';
        }).join('');
        dropdown.querySelectorAll('button').forEach(btn => btn.addEventListener('click', selectPlace));
        dropdown.classList.remove('hidden');
    }

    function selectPlace(e) {
        const btn = e.currentTarget;
        locationInput.value = btn.dataset.name;
        latInput.value      = parseFloat(btn.dataset.lat).toFixed(6);
        lngInput.value      = parseFloat(btn.dataset.lon).toFixed(6);

        const countryInput = document.getElementById('country-input');
        const stateInput   = document.getElementById('state-input');

        if (countryInput && btn.dataset.country) {
            const option = Array.from(countryInput.options).find(opt =>
                opt.value.toLowerCase() === btn.dataset.country.toLowerCase() ||
                opt.value.toLowerCase().includes(btn.dataset.country.toLowerCase())
            );
            if (option) {
                countryInput.value = option.value;
                if (window.fetchStates) window.fetchStates(option.value, btn.dataset.state);
            } else {
                countryInput.value = "";
                if (stateInput) stateInput.innerHTML = '<option value="">Select State...</option>';
            }
        }

        coordsStatus.innerHTML = '<span class="text-emerald-400 font-medium">✔ Captured: ' + parseFloat(btn.dataset.lat).toFixed(5) + ', ' + parseFloat(btn.dataset.lon).toFixed(5) + '</span>';
        coordsStatus.classList.remove('hidden');
        hideDropdown();
    }

    function hideDropdown() {
        dropdown.classList.add('hidden');
        dropdown.innerHTML = '';
    }

    document.addEventListener('click', function (e) {
        if (!locationInput.contains(e.target) && !dropdown.contains(e.target)) {
            hideDropdown();
        }
    });

    locationInput.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') hideDropdown();
    });

    // Dynamic Price Label Update
    const chargeUnitSelect = document.getElementById('id_charge_unit') || document.getElementById('charge-unit-select');
    const priceLabel = document.getElementById('price-label');
    function updatePriceLabel() {
        if (!chargeUnitSelect || !priceLabel) return;
        const val = chargeUnitSelect.value;
        if (val === 'hourly') {
            priceLabel.innerHTML = 'Price Per Hour (₦)';
        } else if (val === 'daily') {
            priceLabel.innerHTML = 'Price Per Day (₦)';
        } else {
            priceLabel.innerHTML = 'Price Per Slot (₦)';
        }
    }
    if (chargeUnitSelect && priceLabel) {
        chargeUnitSelect.addEventListener('change', updatePriceLabel);
        updatePriceLabel();
    }

    // Dynamic Aspect Ratio Calculation
    const widthInput = document.getElementById('screen-width-input');
    const heightInput = document.getElementById('screen-height-input');
    const ratioBadge = document.getElementById('aspect-ratio-badge');
    function gcd(a, b) {
        return b == 0 ? a : gcd(b, a % b);
    }
    function updateAspectRatio() {
        const w = parseInt(widthInput.value) || 0;
        const h = parseInt(heightInput.value) || 0;
        if (w > 0 && h > 0) {
            const divisor = gcd(w, h);
            const rW = w / divisor;
            const rH = h / divisor;
            const orientation = w > h ? 'Landscape' : w < h ? 'Portrait' : 'Square';
            ratioBadge.textContent = `Aspect Ratio: ${rW}:${rH} (${orientation})`;
        } else {
            ratioBadge.textContent = 'Aspect Ratio: --';
        }
    }
    if (widthInput && heightInput && ratioBadge) {
        widthInput.addEventListener('input', updateAspectRatio);
        heightInput.addEventListener('input', updateAspectRatio);
        updateAspectRatio();
    }

    // Country & State Dynamic Loading
    const countrySelect = document.getElementById('country-input');
    const stateSelect   = document.getElementById('state-input');
    function fetchStates(country, selectedState = '') {
        if (!stateSelect) return;
        stateSelect.innerHTML = '<option value="">Loading States...</option>';
        if (!country) {
            stateSelect.innerHTML = '<option value="">Select State...</option>';
            return;
        }
        fetch('https://countriesnow.space/api/v0.1/countries/states', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ country: country })
        })
        .then(res => res.json())
        .then(result => {
            stateSelect.innerHTML = '<option value="">Select State...</option>';
            if (result.error) return;
            const states = result.data.states || [];
            states.sort((a, b) => a.name.localeCompare(b.name));
            states.forEach(s => {
                const opt = document.createElement('option');
                opt.value = s.name;
                opt.textContent = s.name;
                if (selectedState && (s.name.toLowerCase() === selectedState.toLowerCase() ||
                                       s.name.toLowerCase().includes(selectedState.toLowerCase()) ||
                                       selectedState.toLowerCase().includes(s.name.toLowerCase()))) {
                    opt.selected = true;
                }
                stateSelect.appendChild(opt);
            });
        })
        .catch(err => {
            console.error('Error fetching states:', err);
            stateSelect.innerHTML = '<option value="">Select State...</option>';
        });
    }
    window.fetchStates = fetchStates;

    if (countrySelect && stateSelect) {
        const initialCountry = countrySelect.dataset.initial;
        const initialState = stateSelect.dataset.initial;
        fetch('https://countriesnow.space/api/v0.1/countries')
            .then(res => res.json())
            .then(result => {
                if (result.error) return;
                const countries = result.data || [];
                countries.sort((a, b) => a.country.localeCompare(b.country));
                countries.forEach(c => {
                    const opt = document.createElement('option');
                    opt.value = c.country;
                    opt.textContent = c.country;
                    if (initialCountry && c.country.toLowerCase() === initialCountry.toLowerCase()) {
                        opt.selected = true;
                    }
                    countrySelect.appendChild(opt);
                });
                if (initialCountry) {
                    fetchStates(initialCountry, initialState);
                }
            })
            .catch(err => console.error('Error fetching countries:', err));
        countrySelect.addEventListener('change', function () {
            fetchStates(this.value);
        });
    }

    // Drag & Drop Setup
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('media-file-input');
    if (dropZone && fileInput) {
        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                dropZone.classList.add('border-accent', 'bg-white/10');
            }, false);
        });
        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                dropZone.classList.remove('border-accent', 'bg-white/10');
            }, false);
        });
        dropZone.addEventListener('drop', (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;
            if (files.length) {
                fileInput.files = files;
                previewSelectedMedia(fileInput);
            }
        });
    }
}());

function detectLocation() {
    const btn = document.getElementById('detect-location-btn');
    const statusText = document.getElementById('coords-status');
    const latInput = document.getElementById('lat-input');
    const lngInput = document.getElementById('lng-input');
    const locationInput = document.getElementById('location-autocomplete');

    if (!navigator.geolocation) {
        statusText.innerHTML = '<span class="text-red-400">❌ Geolocation is not supported by your browser</span>';
        statusText.classList.remove('hidden');
        return;
    }

    btn.disabled = true;
    const originalContent = btn.innerHTML;
    btn.innerHTML = `
        <svg class="animate-spin h-4 w-4 text-accent" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <span class="hidden sm:inline">Detecting...</span>
    `;
    statusText.innerHTML = '<span class="text-white/60">📍 Requesting GPS coordinates...</span>';
    statusText.classList.remove('hidden');

    navigator.geolocation.getCurrentPosition(
        function (position) {
            const lat = position.coords.latitude;
            const lng = position.coords.longitude;
            latInput.value = lat.toFixed(6);
            lngInput.value = lng.toFixed(6);
            statusText.innerHTML = `<span class="text-white/60">📍 GPS captured. Resolving address...</span>`;

            const url = `https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}&addressdetails=1`;

            fetch(url, {
                headers: {
                    'Accept-Language': 'en',
                    'User-Agent': 'AdversApp/1.0'
                }
            })
            .then(res => res.json())
            .then(data => {
                if (data && data.display_name) {
                    locationInput.value = data.display_name;

                    if (data.address) {
                        const countryInput = document.getElementById('country-input');
                        const stateInput   = document.getElementById('state-input');
                        if (countryInput && data.address.country) {
                            const option = Array.from(countryInput.options).find(opt =>
                                opt.value.toLowerCase() === data.address.country.toLowerCase() ||
                                opt.value.toLowerCase().includes(data.address.country.toLowerCase())
                            );
                            if (option) {
                                countryInput.value = option.value;
                                if (window.fetchStates) window.fetchStates(option.value, data.address.state);
                            }
                        }
                    }
                }
                statusText.innerHTML = `<span class="text-emerald-400 font-medium">✔ Captured: ${lat.toFixed(5)}, ${lng.toFixed(5)}</span>`;
                btn.disabled = false;
                btn.innerHTML = originalContent;
            })
            .catch(() => {
                statusText.innerHTML = `<span class="text-emerald-400 font-medium">✔ Captured: ${lat.toFixed(5)}, ${lng.toFixed(5)}</span>`;
                btn.disabled = false;
                btn.innerHTML = originalContent;
            });
        },
        function (error) {
            statusText.innerHTML = `<span class="text-red-400">❌ Error capturing location (${error.message})</span>`;
            btn.disabled = false;
            btn.innerHTML = originalContent;
        }
    );
}

function previewSelectedMedia(input) {
    if (input.files && input.files[0]) {
        const file = input.files[0];
        const placeholder = document.getElementById('media-preview-placeholder');
        const container = document.getElementById('media-preview-container');
        const img = document.getElementById('media-preview-img');
        const video = document.getElementById('media-preview-video');

        if (placeholder) placeholder.classList.add('hidden');
        if (container) container.classList.remove('hidden');

        const reader = new FileReader();
        reader.onload = function (e) {
            if (file.type.startsWith('video/')) {
                if (img) img.classList.add('hidden');
                if (video) {
                    video.src = e.target.result;
                    video.classList.remove('hidden');
                }
            } else {
                if (video) video.classList.add('hidden');
                if (img) {
                    img.src = e.target.result;
                    img.classList.remove('hidden');
                }
            }
        };
        reader.readAsDataURL(file);
    }
}