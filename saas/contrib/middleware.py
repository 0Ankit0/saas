from django.shortcuts import  render


class PublicAdminOnlyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/admin/"):
            if request.tenant.schema_name != "public":
                return render(request, "403.html", status=403)

        return self.get_response(request)