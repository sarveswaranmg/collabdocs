import time


class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = time.perf_counter()
        response = None
        try:
            response = self.get_response(request)
            return response
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            status_code = response.status_code if response is not None else 500
            print(f"{request.method} {request.path} | Status: {status_code} | Time: {elapsed_ms:.2f} ms")
