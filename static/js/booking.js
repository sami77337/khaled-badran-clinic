(() => {
    "use strict";

    const form = document.querySelector("[data-booking-patient-form]");
    if (!form) {
        return;
    }

    const arabicDigits = "٠١٢٣٤٥٦٧٨٩";
    const persianDigits = "۰۱۲۳۴۵۶۷۸۹";
    const toAsciiDigits = (value) => value
        .replace(/[٠-٩]/g, (digit) => String(arabicDigits.indexOf(digit)))
        .replace(/[۰-۹]/g, (digit) => String(persianDigits.indexOf(digit)));
    const compactNumber = (value) => {
        let compact = toAsciiDigits(String(value || "").trim()).replace(/[\s\-().]/g, "");
        if (compact.startsWith("00")) {
            compact = `+${compact.slice(2)}`;
        }
        return compact;
    };

    const controls = Array.from(form.querySelectorAll("[data-booking-phone-control]"));
    const closeControl = (control, { restoreFocus = false } = {}) => {
        const trigger = control.querySelector("[data-booking-country-trigger]");
        const menu = control.querySelector("[data-booking-country-menu]");
        if (!trigger || !menu || menu.hidden) {
            return;
        }
        menu.hidden = true;
        trigger.setAttribute("aria-expanded", "false");
        control.classList.remove("is-open");
        if (restoreFocus) {
            trigger.focus();
        }
    };

    const closeOthers = (activeControl) => {
        controls.forEach((control) => {
            if (control !== activeControl) {
                closeControl(control);
            }
        });
    };

    controls.forEach((control) => {
        const trigger = control.querySelector("[data-booking-country-trigger]");
        const flag = control.querySelector("[data-booking-country-flag]");
        const dial = control.querySelector("[data-booking-country-dial]");
        const menu = control.querySelector("[data-booking-country-menu]");
        const search = control.querySelector("[data-booking-country-search]");
        const empty = control.querySelector("[data-booking-country-empty]");
        const input = control.querySelector("input[type='text'], input[type='tel']");
        const options = Array.from(control.querySelectorAll("[data-booking-country-option]"));

        if (!trigger || !flag || !dial || !menu || !search || !input || !options.length) {
            return;
        }

        const setCountry = (option) => {
            options.forEach((candidate) => {
                candidate.setAttribute("aria-selected", String(candidate === option));
            });
            control.dataset.bookingDialCode = option.dataset.countryDial;
            control.dataset.bookingCountryCode = option.dataset.countryCode;
            flag.textContent = option.dataset.countryFlag;
            dial.textContent = option.dataset.countryDial;
        };

        const findCountry = (number) => options
            .slice()
            .sort((left, right) => right.dataset.countryDial.length - left.dataset.countryDial.length)
            .find((option) => number.startsWith(option.dataset.countryDial));

        const parseInitialValue = () => {
            let number = compactNumber(input.value);
            if (!number) {
                setCountry(options.find((option) => option.dataset.countryDial === "+962") || options[0]);
                return;
            }
            if (!number.startsWith("+") && number.startsWith("962")) {
                number = `+${number}`;
            }
            const matchingCountry = number.startsWith("+") ? findCountry(number) : null;
            if (matchingCountry) {
                setCountry(matchingCountry);
                input.value = number.slice(matchingCountry.dataset.countryDial.length);
                return;
            }
            setCountry(options.find((option) => option.dataset.countryDial === "+962") || options[0]);
            input.value = number;
        };

        const showAllOptions = () => {
            options.forEach((option) => {
                option.hidden = false;
            });
            empty.hidden = true;
        };

        const openMenu = () => {
            if (trigger.disabled) {
                return;
            }
            closeOthers(control);
            menu.hidden = false;
            trigger.setAttribute("aria-expanded", "true");
            control.classList.add("is-open");
            search.value = "";
            showAllOptions();
            search.focus();
        };

        const chooseOption = (option) => {
            setCountry(option);
            closeControl(control, { restoreFocus: true });
        };

        trigger.addEventListener("click", () => {
            if (menu.hidden) {
                openMenu();
            } else {
                closeControl(control, { restoreFocus: true });
            }
        });

        trigger.addEventListener("keydown", (event) => {
            if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                openMenu();
            }
        });

        search.addEventListener("input", () => {
            const query = toAsciiDigits(search.value).trim().toLocaleLowerCase();
            let visibleCount = 0;
            options.forEach((option) => {
                const matches = !query || option.dataset.countrySearch.toLocaleLowerCase().includes(query);
                option.hidden = !matches;
                visibleCount += matches ? 1 : 0;
            });
            empty.hidden = visibleCount !== 0;
        });

        search.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                event.preventDefault();
                closeControl(control, { restoreFocus: true });
            } else if (event.key === "ArrowDown") {
                const firstVisibleOption = options.find((option) => !option.hidden);
                if (firstVisibleOption) {
                    event.preventDefault();
                    firstVisibleOption.focus();
                }
            }
        });

        options.forEach((option, index) => {
            option.addEventListener("click", () => chooseOption(option));
            option.addEventListener("keydown", (event) => {
                if (event.key === "Escape") {
                    event.preventDefault();
                    closeControl(control, { restoreFocus: true });
                    return;
                }
                if (event.key !== "ArrowDown" && event.key !== "ArrowUp") {
                    return;
                }
                event.preventDefault();
                const visibleOptions = options.filter((candidate) => !candidate.hidden);
                const currentIndex = visibleOptions.indexOf(option);
                const increment = event.key === "ArrowDown" ? 1 : -1;
                const nextIndex = (currentIndex + increment + visibleOptions.length) % visibleOptions.length;
                (visibleOptions[nextIndex] || options[index]).focus();
            });
        });

        input.addEventListener("change", () => {
            const number = compactNumber(input.value);
            const matchingCountry = number.startsWith("+") ? findCountry(number) : null;
            if (matchingCountry) {
                setCountry(matchingCountry);
                input.value = number.slice(matchingCountry.dataset.countryDial.length);
            }
        });

        control.bookingComposeNumber = () => {
            const number = compactNumber(input.value);
            if (!number) {
                input.value = "";
                return;
            }
            if (number.startsWith("+")) {
                input.value = number;
                return;
            }
            const selectedDial = control.dataset.bookingDialCode || control.dataset.bookingDefaultDialCode;
            const selectedCountry = control.dataset.bookingCountryCode;
            const localNumber = selectedCountry === "JO" && number.startsWith("0")
                ? number.slice(1)
                : number;
            input.value = `${selectedDial}${localNumber}`;
        };

        parseInitialValue();
    });

    const sameAsPhone = form.querySelector("[name='same_as_phone']");
    const whatsappField = form.querySelector("[data-booking-whatsapp-field]");
    const whatsappControl = whatsappField?.querySelector("[data-booking-phone-control]");
    const whatsappInput = whatsappField?.querySelector("[name='whatsapp_phone']");
    const whatsappTrigger = whatsappControl?.querySelector("[data-booking-country-trigger]");

    const syncWhatsappState = () => {
        if (!sameAsPhone || !whatsappField || !whatsappInput || !whatsappTrigger) {
            return;
        }
        const isSame = sameAsPhone.checked;
        whatsappField.classList.toggle("is-disabled", isSame);
        whatsappField.setAttribute("aria-disabled", String(isSame));
        whatsappInput.disabled = isSame;
        whatsappTrigger.disabled = isSame;
        if (isSame && whatsappControl) {
            closeControl(whatsappControl);
        }
    };

    sameAsPhone?.addEventListener("change", syncWhatsappState);
    syncWhatsappState();

    document.addEventListener("click", (event) => {
        controls.forEach((control) => {
            if (!control.contains(event.target)) {
                closeControl(control);
            }
        });
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            controls.forEach((control) => closeControl(control));
        }
    });

    form.addEventListener("submit", () => {
        controls.forEach((control) => {
            const isDisabled = control.querySelector("input")?.disabled;
            if (!isDisabled && typeof control.bookingComposeNumber === "function") {
                control.bookingComposeNumber();
            }
        });
    });
})();
