from django import forms
from django.contrib.auth.forms import PasswordChangeForm
from django.core.validators import MaxLengthValidator

from apps.core.content_validation import validate_public_text
from apps.core.doctor_sections import BUILTIN_SECTIONS
from apps.core.models import DoctorPageContent, DoctorPageSection
from apps.core.public_copy import HOME_VISIBILITY, copy_definitions


def bilingual_fields(fields):
    for name, field in fields.items():
        if name.endswith(("_ar", "_en")):
            field.widget.attrs.update(
                dir="rtl" if name.endswith("_ar") else "ltr", lang=name[-2:]
            )


class DashboardPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        labels = (
            ("كلمة المرور الحالية", "كلمة المرور الجديدة", "تأكيد كلمة المرور الجديدة")
            if language == "ar"
            else (
                "Current password",
                "New password",
                "Confirm new password",
            )
        )
        for name, label in zip(
            ("old_password", "new_password1", "new_password2"), labels
        ):
            self.fields[name].label = label


class DoctorBioForm(forms.ModelForm):
    class Meta:
        model = DoctorPageContent
        fields = (
            "hero_summary_ar",
            "hero_summary_en",
            "credential_label_ar",
            "credential_label_en",
            "professional_bio_ar",
            "professional_bio_en",
        )

    def __init__(self, *args, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        labels = {
            "hero_summary": ("الوصف المختصر", "Short summary"),
            "credential_label": ("المؤهلات المختصرة", "Credential label"),
            "professional_bio": ("النبذة المهنية", "Professional biography"),
        }
        from apps.core.templatetags.doctor_content import doctor_default_content

        defaults = {
            lang: doctor_default_content(self.instance.doctor, lang)
            for lang in ("ar", "en")
        }
        for name, field in self.fields.items():
            base, lang = name.rsplit("_", 1)
            field.label = labels[base][language == "en"] + (
                " — العربية" if lang == "ar" else " — English"
            )
            field.validators.append(validate_public_text)
            field.validators.append(MaxLengthValidator(12000))
            field.max_length = 12000
            field.widget.attrs.update(rows=4, maxlength=12000)
            field.widget.attrs["placeholder"] = defaults[lang][
                "bio" if base == "professional_bio" else base
            ]
        bilingual_fields(self.fields)


class DoctorSectionForm(forms.ModelForm):
    class Meta:
        model = DoctorPageSection
        fields = (
            "title_ar",
            "title_en",
            "content_ar",
            "content_en",
            "presentation",
            "display_order",
            "is_visible",
            "is_archived",
        )
        widgets = {
            "content_ar": forms.Textarea(attrs={"rows": 7}),
            "content_en": forms.Textarea(attrs={"rows": 7}),
        }

    def __init__(self, *args, language="ar", legacy=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.legacy = legacy
        labels = {
            "title_ar": ("العنوان — العربية", "Title — Arabic"),
            "title_en": ("العنوان — English", "Title — English"),
            "content_ar": ("المحتوى — العربية", "Content — Arabic"),
            "content_en": ("المحتوى — English", "Content — English"),
            "presentation": ("طريقة العرض", "Presentation"),
            "display_order": ("ترتيب العرض", "Display order"),
            "is_visible": ("ظاهر على الموقع", "Visible on the website"),
            "is_archived": ("مؤرشف", "Archived"),
        }
        for name, field in self.fields.items():
            field.label = labels[name][language == "en"]
        if language == "ar":
            self.fields["presentation"].choices = [
                ("TEXT", "نص"),
                ("LIST", "قائمة"),
                ("CHIPS", "فقاعات"),
                ("CARDS", "بطاقات"),
            ]
        if self.instance.key:
            del self.fields["is_archived"]
            from apps.core.templatetags.doctor_content import doctor_default_content

            for lang in ("ar", "en"):
                self.fields[f"title_{lang}"].widget.attrs["placeholder"] = (
                    BUILTIN_SECTIONS[self.instance.key][1 if lang == "ar" else 2]
                )
                self.initial[f"content_{lang}"] = getattr(
                    legacy, f"{self.instance.key}_{lang}", ""
                )
                values = doctor_default_content(self.instance.doctor, lang)[
                    self.instance.key
                ]
                if self.instance.key == "memberships":
                    values = [
                        " | ".join(
                            part for part in (item["label"], item["acronym"]) if part
                        )
                        for item in values
                    ]
                self.fields[f"content_{lang}"].widget.attrs["placeholder"] = "\n".join(
                    values
                )
        self.fields["display_order"].help_text = (
            "الأرقام الأصغر تظهر أولًا."
            if language == "ar"
            else "Lower numbers appear first."
        )
        for lang in ("ar", "en"):
            self.fields[f"content_{lang}"].help_text = (
                "للقوائم والفقاعات والبطاقات: عنصر واحد في كل سطر."
                if language == "ar"
                else "For lists, chips and cards: one item per line."
            )
        if self.instance.key == "memberships":
            for lang in ("ar", "en"):
                self.fields[f"content_{lang}"].help_text += (
                    " الاسم | الاختصار" if language == "ar" else " Label | ACRONYM"
                )
        self.language = language
        bilingual_fields(self.fields)

    def clean(self):
        data = super().clean()
        if (
            not self.instance.key
            and data.get("is_visible")
            and not data.get("is_archived")
        ):
            for name in ("title_ar", "title_en", "content_ar", "content_en"):
                if not data.get(name):
                    self.add_error(
                        name,
                        "أكمل العربية والإنجليزية قبل النشر."
                        if self.language == "ar"
                        else "Complete Arabic and English before publishing.",
                    )
        return data

    def save(self, commit=True):
        if not self.instance.key:
            return super().save(commit=commit)
        # Keep the existing DoctorPageContent fields as the single source of truth.
        for lang in ("ar", "en"):
            setattr(
                self.legacy,
                f"{self.instance.key}_{lang}",
                self.cleaned_data[f"content_{lang}"],
            )
            setattr(self.instance, f"content_{lang}", "")
        if commit:
            self.legacy.save()
        return super().save(commit=commit)


class PublicCopyForm(forms.Form):
    def __init__(self, *args, page, overrides, language="ar", doctor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.copy_keys = [
            key for key in copy_definitions() if key.startswith(page + ".")
        ]
        self.visibility_keys = list(HOME_VISIBILITY) if page == "home" else []
        for key in self.copy_keys:
            defaults = copy_definitions()[key]
            if key == "home.bio" and doctor:
                defaults = tuple(
                    getattr(doctor, f"bio_{lang}") or defaults[index]
                    for index, lang in enumerate(("ar", "en"))
                )
            row = overrides.get(key)
            for index, lang in enumerate(("ar", "en")):
                name = self.field_name(key, lang)
                self.fields[name] = forms.CharField(
                    required=False,
                    max_length=6000,
                    validators=[validate_public_text],
                    label=(
                        defaults[language == "en"][:100]
                        + (" — العربية" if lang == "ar" else " — English")
                    ),
                    initial=getattr(row, f"text_{lang}", ""),
                    widget=forms.Textarea(
                        attrs={
                            "rows": 2,
                            "placeholder": defaults[index],
                            "dir": "rtl" if lang == "ar" else "ltr",
                            "lang": lang,
                        }
                    ),
                )
        for key in self.visibility_keys:
            self.fields[self.field_name(key)] = forms.BooleanField(
                required=False,
                label=HOME_VISIBILITY[key][language == "en"],
                initial=overrides[key].is_visible if key in overrides else True,
            )

    @staticmethod
    def field_name(key, language=None):
        return key.replace(".", "_") + (f"_{language}" if language else "")
