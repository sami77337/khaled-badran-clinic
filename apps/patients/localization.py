from functools import partial, wraps

from django.utils.translation import override


def use_page_language(view=None, *, language_getter=None):
    """Scope form construction, validation and synchronous rendering to the page.

    Portal routes supply a language keyword; the staff view supplies its existing
    query-language resolver. Restore the request locale when the view returns.
    """
    if view is None:
        return partial(use_page_language, language_getter=language_getter)

    @wraps(view)
    def localized(request, *args, **kwargs):
        language = language_getter(request) if language_getter else kwargs.get("language", "ar")
        with override("en" if language == "en" else "ar"):
            return view(request, *args, **kwargs)

    return localized
