(() => {
    "use strict";

    const relativeUrl = (url) => `${url.pathname}${url.search}${url.hash}`;
    const buildUrl = (base, parameters) => {
        const url = new URL(base, window.location.href);
        Object.entries(parameters).forEach(([key, value]) => {
            if (value === null || value === undefined || value === "") {
                url.searchParams.delete(key);
            } else {
                url.searchParams.set(key, value);
            }
        });
        return relativeUrl(url);
    };

    const preserveViewport = (update) => {
        const left = window.scrollX;
        const top = window.scrollY;
        update();
        window.requestAnimationFrame(() => {
            const root = document.documentElement;
            const previousBehavior = root.style.scrollBehavior;
            root.style.scrollBehavior = "auto";
            window.scrollTo(left, top);
            root.style.scrollBehavior = previousBehavior;
        });
    };

    const replaceHistory = (href) => {
        if (!window.history?.replaceState) {
            return;
        }
        const url = new URL(href, window.location.href);
        window.history.replaceState(window.history.state, "", relativeUrl(url));
    };

    const syncLanguageSwitches = (parameters) => {
        document.querySelectorAll("a[hreflang]").forEach((link) => {
            link.setAttribute("href", buildUrl(link.href, parameters));
        });
    };

    const setActionState = (control, href) => {
        if (!control) {
            return null;
        }
        const requiredTag = href ? "A" : "SPAN";
        let nextControl = control;
        if (control.tagName !== requiredTag) {
            nextControl = document.createElement(requiredTag.toLowerCase());
            Array.from(control.attributes).forEach((attribute) => {
                if (attribute.name === "href" || attribute.name === "aria-disabled") {
                    return;
                }
                nextControl.setAttribute(attribute.name, attribute.value);
            });
            nextControl.innerHTML = control.innerHTML;
            control.replaceWith(nextControl);
        }

        nextControl.classList.toggle("is-disabled", !href);
        if (href) {
            nextControl.setAttribute("href", href);
            nextControl.removeAttribute("aria-disabled");
        } else {
            nextControl.removeAttribute("href");
            nextControl.setAttribute("aria-disabled", "true");
        }
        return nextControl;
    };

    const serviceStep = document.querySelector("[data-booking-service-step]");
    if (serviceStep) {
        const serviceOptions = Array.from(serviceStep.querySelectorAll("[data-booking-visit-option]"));
        const additionalServices = serviceStep.querySelector("[data-booking-additional-services]");
        const moreControl = serviceStep.querySelector("[data-booking-service-more]");
        const moreToggle = moreControl?.querySelector("summary");
        const slotsUrl = serviceStep.dataset.bookingSlotsUrl;
        let continueControl = serviceStep.querySelector("[data-booking-continue]");

        const selectedAdditionalService = () => additionalServices?.querySelector(
            "[data-booking-visit-option].is-selected"
        );

        serviceOptions.forEach((option) => {
            option.addEventListener("click", (event) => {
                event.preventDefault();
                preserveViewport(() => {
                    serviceOptions.forEach((candidate) => {
                        const isSelected = candidate === option;
                        candidate.classList.toggle("is-selected", isSelected);
                        if (isSelected) {
                            candidate.setAttribute("aria-current", "true");
                        } else {
                            candidate.removeAttribute("aria-current");
                        }
                    });

                    if (moreControl && additionalServices?.contains(option)) {
                        moreControl.open = true;
                    }

                    const visitType = option.dataset.bookingServiceId;
                    continueControl = setActionState(
                        continueControl,
                        buildUrl(slotsUrl, { visit_type: visitType })
                    );
                    replaceHistory(option.href);
                    syncLanguageSwitches({ visit_type: visitType });
                });
            });
        });

        moreToggle?.addEventListener("click", (event) => {
            if (moreControl.open && selectedAdditionalService()) {
                event.preventDefault();
                return;
            }
            preserveViewport(() => {});
        });

        moreControl?.addEventListener("toggle", () => {
            if (!moreControl.open && selectedAdditionalService()) {
                moreControl.open = true;
            }
        });
    }

    const slotStep = document.querySelector("[data-booking-slot-step]");
    if (slotStep) {
        const dateButtons = Array.from(slotStep.querySelectorAll("[data-booking-date-group]"));
        const timePanels = Array.from(slotStep.querySelectorAll("[data-booking-time-panel]"));
        const slotButtons = Array.from(slotStep.querySelectorAll("[data-booking-slot]"));
        const visitType = slotStep.dataset.bookingVisitTypeId;
        const confirmUrl = slotStep.dataset.bookingConfirmUrl;
        let continueControl = slotStep.querySelector("[data-booking-slot-continue]");

        const clearSelectedTime = () => {
            slotButtons.forEach((slot) => {
                slot.classList.remove("is-selected");
                slot.removeAttribute("aria-current");
                slot.removeAttribute("data-booking-selected-time");
                const check = slot.querySelector(".booking-slot-check");
                if (check) {
                    check.hidden = true;
                }
            });
            continueControl = setActionState(continueControl, null);
        };

        dateButtons.forEach((button) => {
            button.addEventListener("click", (event) => {
                event.preventDefault();
                preserveViewport(() => {
                    const selectedDate = button.dataset.bookingDate;
                    dateButtons.forEach((candidate) => {
                        const isSelected = candidate === button;
                        candidate.classList.toggle("is-selected", isSelected);
                        candidate.toggleAttribute("data-booking-selected-date", isSelected);
                        if (isSelected) {
                            candidate.setAttribute("aria-current", "date");
                        } else {
                            candidate.removeAttribute("aria-current");
                        }
                    });
                    timePanels.forEach((panel) => {
                        panel.hidden = panel.dataset.bookingDate !== selectedDate;
                    });
                    clearSelectedTime();
                    replaceHistory(button.href);
                    syncLanguageSwitches({
                        visit_type: visitType,
                        date: selectedDate,
                        starts_at: null,
                    });
                });
            });
        });

        slotButtons.forEach((slot) => {
            slot.addEventListener("click", (event) => {
                event.preventDefault();
                preserveViewport(() => {
                    slotButtons.forEach((candidate) => {
                        const isSelected = candidate === slot;
                        candidate.classList.toggle("is-selected", isSelected);
                        candidate.toggleAttribute("data-booking-selected-time", isSelected);
                        if (isSelected) {
                            candidate.setAttribute("aria-current", "time");
                        } else {
                            candidate.removeAttribute("aria-current");
                        }
                        const check = candidate.querySelector(".booking-slot-check");
                        if (check) {
                            check.hidden = !isSelected;
                        }
                    });

                    const startsAt = slot.dataset.bookingSlotValue;
                    const selectedDate = slot.closest("[data-booking-time-panel]")?.dataset.bookingDate;
                    continueControl = setActionState(
                        continueControl,
                        buildUrl(confirmUrl, {
                            visit_type: visitType,
                            starts_at: startsAt,
                        })
                    );
                    replaceHistory(slot.href);
                    syncLanguageSwitches({
                        visit_type: visitType,
                        date: selectedDate,
                        starts_at: startsAt,
                    });
                });
            });
        });
    }

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
        const hint = control.querySelector("[data-booking-phone-hint]");
        const input = control.querySelector("input[type='text'], input[type='tel']");
        const options = Array.from(control.querySelectorAll("[data-booking-country-option]"));

        if (!trigger || !flag || !dial || !menu || !search || !input || !options.length) {
            return;
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

        const displayInternationalNumber = (number, matchingCountry) => {
            setCountry(matchingCountry);
            input.value = stripDomesticPrefix(
                number.slice(matchingCountry.dataset.countryDial.length),
                matchingCountry.dataset.countryNationalPrefix || ""
            );
        };

        const parseInitialValue = () => {
            let number = compactNumber(input.value);
            const defaultCountry = options.find((option) => option.dataset.countryCode === "JO") || options[0];
            if (!number) {
                setCountry(defaultCountry);
                return;
            }
            if (!number.startsWith("+") && number.startsWith("962")) {
                number = `+${number}`;
            }
            const matchingCountry = number.startsWith("+") ? findCountry(number) : null;
            if (matchingCountry) {
                displayInternationalNumber(number, matchingCountry);
                return;
            }
            setCountry(defaultCountry);
            input.value = stripDomesticPrefix(
                number,
                defaultCountry.dataset.countryNationalPrefix || ""
            );
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
            input.value = stripDomesticPrefix(
                compactNumber(input.value),
                option.dataset.countryNationalPrefix || ""
            );
            closeControl(control, { restoreFocus: true });
            input.focus({ preventScroll: true });
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
                displayInternationalNumber(number, matchingCountry);
            } else {
                input.value = stripDomesticPrefix(
                    number,
                    control.dataset.bookingNationalPrefix || ""
                );
            }
        });

        control.bookingComposeNumber = () => {
            let number = compactNumber(input.value);
            if (!number) {
                return "";
            }

            let selectedDial = control.dataset.bookingDialCode || control.dataset.bookingDefaultDialCode;
            let domesticPrefix = control.dataset.bookingNationalPrefix || "";
            if (number.startsWith("+")) {
                const matchingCountry = findCountry(number);
                if (!matchingCountry) {
                    return number;
                }
                selectedDial = matchingCountry.dataset.countryDial;
                domesticPrefix = matchingCountry.dataset.countryNationalPrefix || "";
                number = number.slice(matchingCountry.dataset.countryDial.length);
            }

            const normalizedLocalNumber = stripDomesticPrefix(
                number,
                domesticPrefix
            );
            return `${selectedDial}${normalizedLocalNumber}`;
        };

        parseInitialValue();
    });

    const sameAsPhone = form.querySelector("[name='same_as_phone'], [name='same_as_contact']");
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
        whatsappField.hidden = isSame;
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

    form.addEventListener("formdata", (event) => {
        controls.forEach((control) => {
            const input = control.querySelector("input[type='text'], input[type='tel']");
            if (
                input?.name
                && !input.disabled
                && typeof control.bookingComposeNumber === "function"
            ) {
                event.formData.set(input.name, control.bookingComposeNumber());
            }
        });
    });
})();
