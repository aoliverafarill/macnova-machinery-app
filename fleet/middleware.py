"""
Custom middleware to force Spanish as default language for operator forms.
This is critical because operators don't speak English.
"""
from django.utils import translation
from django.utils.deprecation import MiddlewareMixin


class ForceSpanishDefaultMiddleware(MiddlewareMixin):
    """
    Forces Spanish as default language for operator-facing pages.
    Only allows English if explicitly selected via language switcher.
    """
    
    def process_request(self, request):
        # Only apply to operator form URLs (QR code access)
        if request.path.startswith('/m/') and len(request.path.split('/')) == 3:
            # Check if language is explicitly set in session (from language switcher)
            language = request.session.get('django_language')
            
            # If no explicit language preference, force Spanish
            if not language or language not in ['es', 'en']:
                translation.activate('es')
                request.LANGUAGE_CODE = 'es'
                request.session['django_language'] = 'es'
            elif language == 'en':
                # Allow English only if explicitly selected
                translation.activate('en')
                request.LANGUAGE_CODE = 'en'
            else:
                # Default to Spanish
                translation.activate('es')
                request.LANGUAGE_CODE = 'es'
                request.session['django_language'] = 'es'
        
        return None

