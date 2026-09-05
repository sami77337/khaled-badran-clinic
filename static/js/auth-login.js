(() => {
    "use strict";

    const root = document.querySelector("[data-auth-login], [data-auth-register]");
    if (!root) {
        return;
    }

    const tabs = Array.from(root.querySelectorAll("[data-auth-role]"));
    const panels = Array.from(root.querySelectorAll("[data-auth-panel]"));

    const selectRole = (role, { updateUrl = false } = {}) => {
        const selectedTab = tabs.find((tab) => tab.dataset.authRole === role) || tabs[0];
        if (!selectedTab) {
            return;
        }

        root.dataset.selectedRole = selectedTab.dataset.authRole;
        tabs.forEach((tab) => {
            const selected = tab === selectedTab;
            tab.classList.toggle("is-selected", selected);
            tab.setAttribute("aria-selected", String(selected));
            tab.tabIndex = selected ? 0 : -1;
        });
        panels.forEach((panel) => {
            const selected = panel.dataset.authPanel === selectedTab.dataset.authRole;
            panel.hidden = !selected;
            panel.setAttribute("aria-hidden", String(!selected));
            panel.querySelectorAll("input, button, select, textarea").forEach((control) => {
                control.disabled = !selected;
            });
        });

        if (updateUrl && window.history?.replaceState) {
            window.history.replaceState({}, "", selectedTab.href);
        }
    };

    tabs.forEach((tab, index) => {
        tab.addEventListener("click", (event) => {
            event.preventDefault();
            selectRole(tab.dataset.authRole, { updateUrl: true });
        });
        tab.addEventListener("keydown", (event) => {
            let nextIndex = null;
            if (event.key === "ArrowRight" || event.key === "ArrowDown") {
                nextIndex = (index + 1) % tabs.length;
            } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
                nextIndex = (index - 1 + tabs.length) % tabs.length;
            } else if (event.key === "Home") {
                nextIndex = 0;
            } else if (event.key === "End") {
                nextIndex = tabs.length - 1;
            }
            if (nextIndex === null) {
                return;
            }
            event.preventDefault();
            tabs[nextIndex].focus({ preventScroll: true });
            selectRole(tabs[nextIndex].dataset.authRole, { updateUrl: true });
        });
    });

    selectRole(root.dataset.selectedRole || "patient");

    root.querySelectorAll("[data-password-toggle]").forEach((button) => {
        const input = button.closest(".auth-password-control")?.querySelector("input");
        if (!input) {
            return;
        }
        button.addEventListener("click", () => {
            const show = input.type === "password";
            input.type = show ? "text" : "password";
            button.setAttribute("aria-label", show ? button.dataset.hideLabel : button.dataset.showLabel);
            button.setAttribute("aria-pressed", String(show));
            input.focus({ preventScroll: true });
        });
    });

    const patientForm = root.querySelector("[data-patient-login-form], [data-patient-register-form]");
    if (!patientForm) {
        return;
    }

    const arabicDigits = "٠١٢٣٤٥٦٧٨٩";
    const persianDigits = "۰۱۲۳۴۵۶۷۸۹";
    const toAsciiDigits = (value) => value
        .replace(/[٠-٩]/g, (digit) => String(arabicDigits.indexOf(digit)))
        .replace(/[۰-۹]/g, (digit) => String(persianDigits.indexOf(digit)));
    const compactNumber = (value) => {
        let compact = toAsciiDigits(String(value || "").trim()).replace(/[\s\-()./]/g, "");
        if (compact.startsWith("00")) {
            compact = `+${compact.slice(2)}`;
        }
        return compact;
    };
    const stripDomesticPrefix = (number, domesticPrefix) => (
        domesticPrefix && number.startsWith(domesticPrefix)
            ? number.slice(domesticPrefix.length)
            : number
    );

    const controls = Array.from(patientForm.querySelectorAll("[data-booking-phone-control]"));
    const closeControl = (control, { restoreFocus = false } = {}) => {
        const trigger = control.querySelector("[data-booking-country-trigger]");
        const menu = control.querySelector("[data-booking-country-menu]");
        if (!trigger || !menu || menu.hidden) {
            return;
        }
        menu.hidden = true;
        trigger.setAttribute("aria-expanded", "false");
        control.classList.remove("is-open");
        control.classList.remove("opens-up");
        if (restoreFocus) {
            trigger.focus({ preventScroll: true });
        }
    };

    controls.forEach((control) => {
        const trigger = control.querySelector("[data-booking-country-trigger]");
        const flag = control.querySelector("[data-booking-country-flag]");
        const dial = control.querySelector("[data-booking-country-dial]");
        const menu = control.querySelector("[data-booking-country-menu]");
        const search = control.querySelector("[data-booking-country-search]");
        const empty = control.querySelector("[data-booking-country-empty]");
        const hint = control.querySelector("[data-booking-phone-hint]");
        const input = control.querySelector("input[type='text'], input[type='tel']");
        const options = Array.from(control.querySelectorAll("[data-booking-country-option]"));
        if (!trigger || !flag || !dial || !menu || !search || !input || !options.length) {
            return;
        }

        const phoneViewport = window.matchMedia("(max-width: 40rem)");
        let menuVisibilityFrame = null;
        const keepMobileMenuVisible = () => {
            if (menu.hidden || !phoneViewport.matches) {
                return;
            }
            if (menuVisibilityFrame !== null) {
                window.cancelAnimationFrame(menuVisibilityFrame);
            }
            menuVisibilityFrame = window.requestAnimationFrame(() => {
                menuVisibilityFrame = null;
                if (menu.hidden) {
                    return;
                }
                const viewport = window.visualViewport;
                const viewportTop = viewport?.offsetTop || 0;
                const viewportBottom = viewportTop + (viewport?.height || window.innerHeight);
                const bottomNavigation = document.querySelector("[data-mobile-bottom-navigation]");
                const navigationTop = bottomNavigation?.getBoundingClientRect().top ?? viewportBottom;
                const safeBottom = Math.min(viewportBottom, navigationTop) - 8;
                const safeTop = viewportTop + 8;
                const menuRect = menu.getBoundingClientRect();
                if (menuRect.height <= safeBottom - safeTop && menuRect.bottom > safeBottom) {
                    window.scrollBy({ top: Math.ceil(menuRect.bottom - safeBottom), behavior: "auto" });
                }
            });
        };

        if (window.visualViewport) {
            window.visualViewport.addEventListener("resize", keepMobileMenuVisible);
        } else {
            window.addEventListener("resize", keepMobileMenuVisible);
        }

        if (hint?.id) {
            input.setAttribute("aria-describedby", hint.id);
        }

        const setCountry = (option) => {
            options.forEach((candidate) => {
                candidate.setAttribute("aria-selected", String(candidate === option));
            });
            control.dataset.bookingDialCode = option.dataset.countryDial;
            control.dataset.bookingCountryCode = option.dataset.countryCode;
            control.dataset.bookingNationalPrefix = option.dataset.countryNationalPrefix || "";
            flag.textContent = option.dataset.countryFlag;
            dial.textContent = option.dataset.countryDial;
            input.placeholder = option.dataset.countryExample || "";
            if (hint) {
                hint.textContent = `${control.dataset.bookingExampleLabel}: ${option.dataset.countryExample}`;
            }
        };

        const findCountry = (number) => {
            const matches = options
                .filter((option) => number.startsWith(option.dataset.countryDial))
                .sort((left, right) => right.dataset.countryDial.length - left.dataset.countryDial.length);
            const longestDialLength = matches[0]?.dataset.countryDial.length;
            const longestMatches = matches.filter(
                (option) => option.dataset.countryDial.length === longestDialLength
            );
            return longestMatches.find(
                (option) => option.dataset.countryCode === control.dataset.bookingCountryCode
            ) || longestMatches.find(
                (option) => option.dataset.countryCode === "US"
            ) || longestMatches.find(
                (option) => option.dataset.countryCode === "RU"
            ) || longestMatches[0];
        };

        const displayInternationalNumber = (number, country) => {
            setCountry(country);
            input.value = stripDomesticPrefix(
                number.slice(country.dataset.countryDial.length),
                country.dataset.countryNationalPrefix || ""
            );
        };

        const defaultCountry = options.find((option) => option.dataset.countryCode === "JO") || options[0];
        let initialNumber = compactNumber(input.value);
        if (!initialNumber) {
            setCountry(defaultCountry);
        } else {
            if (!initialNumber.startsWith("+") && initialNumber.startsWith("962")) {
                initialNumber = `+${initialNumber}`;
            }
            const initialCountry = initialNumber.startsWith("+") ? findCountry(initialNumber) : null;
            if (initialCountry) {
                displayInternationalNumber(initialNumber, initialCountry);
            } else {
                setCountry(defaultCountry);
                input.value = stripDomesticPrefix(
                    initialNumber,
                    defaultCountry.dataset.countryNationalPrefix || ""
                );
            }
        }

        const showAllOptions = () => {
            options.forEach((option) => {
                option.hidden = false;
            });
            empty.hidden = true;
        };

        const openMenu = ({ focusSearch = false } = {}) => {
            controls.forEach((candidate) => {
                if (candidate !== control) {
                    closeControl(candidate);
                }
            });
            menu.hidden = false;
            trigger.setAttribute("aria-expanded", "true");
            control.classList.add("is-open");
            const triggerRect = trigger.getBoundingClientRect();
            const menuHeight = menu.getBoundingClientRect().height;
            const spaceBelow = window.innerHeight - triggerRect.bottom;
            const spaceAbove = triggerRect.top;
            control.classList.toggle("opens-up", spaceBelow < menuHeight && spaceAbove > spaceBelow);
            search.value = "";
            showAllOptions();
            keepMobileMenuVisible();
            if (focusSearch) {
                search.focus({ preventScroll: true });
            }
        };

        const chooseOption = (option) => {
            setCountry(option);
            input.value = stripDomesticPrefix(
                compactNumber(input.value),
                option.dataset.countryNationalPrefix || ""
            );
            closeControl(control, { restoreFocus: true });
            input.focus({ preventScroll: true });
        };

        trigger.addEventListener("click", (event) => {
            if (menu.hidden) {
                openMenu({ focusSearch: event.detail === 0 });
            } else {
                closeControl(control, { restoreFocus: true });
            }
        });

        trigger.addEventListener("keydown", (event) => {
            if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                openMenu({ focusSearch: true });
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
                const firstVisible = options.find((option) => !option.hidden);
                if (firstVisible) {
                    event.preventDefault();
                    firstVisible.focus({ preventScroll: true });
                }
            }
        });

        options.forEach((option) => {
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
                const visible = options.filter((candidate) => !candidate.hidden);
                const index = visible.indexOf(option);
                const increment = event.key === "ArrowDown" ? 1 : -1;
                visible[(index + increment + visible.length) % visible.length]?.focus({ preventScroll: true });
            });
        });

        input.addEventListener("change", () => {
            const number = compactNumber(input.value);
            const country = number.startsWith("+") ? findCountry(number) : null;
            if (country) {
                displayInternationalNumber(number, country);
            } else {
                input.value = stripDomesticPrefix(
                    number,
                    control.dataset.bookingNationalPrefix || ""
                );
            }
        });

        control.composePhoneNumber = () => {
            let number = compactNumber(input.value);
            if (!number) {
                return "";
            }
            let dialCode = control.dataset.bookingDialCode || control.dataset.bookingDefaultDialCode;
            let nationalPrefix = control.dataset.bookingNationalPrefix || "";
            if (number.startsWith("+")) {
                const country = findCountry(number);
                if (!country) {
                    return number;
                }
                dialCode = country.dataset.countryDial;
                nationalPrefix = country.dataset.countryNationalPrefix || "";
                number = number.slice(country.dataset.countryDial.length);
            }
            return `${dialCode}${stripDomesticPrefix(number, nationalPrefix)}`;
        };
    });

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

    patientForm.addEventListener("formdata", (event) => {
        controls.forEach((control) => {
            const input = control.querySelector("input[type='text'], input[type='tel']");
            if (input?.name && typeof control.composePhoneNumber === "function") {
                event.formData.set(input.name, control.composePhoneNumber());
            }
        });
    });
})();
