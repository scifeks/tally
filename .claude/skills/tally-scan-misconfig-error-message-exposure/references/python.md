# Python error message exposure patterns

Vulnerable-vs-safe snippets for Python error handling the
`misconfig.error_message_exposure` scanner recognizes. When multiple safe
forms exist, the canonical one is shown first.

## Django custom error views

### Vulnerable

```python
def custom_404_view(request, exception):
    return JsonResponse(
        {"error": str(exception)},
        status=404
    )

def error_view(request):
    try:
        data = get_data()
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
```

### Safe

```python
def custom_404_view(request, exception):
    return JsonResponse(
        {"error": "Resource not found"},
        status=404
    )

def error_view(request):
    try:
        data = get_data()
    except Exception as e:
        logger.exception("Error retrieving data")
        return JsonResponse(
            {"error": "Internal server error"},
            status=500
        )
```

Return a generic error message to the client. Log the full exception
server-side using `logger.exception()` for debugging without exposing
details to the user.

## Flask error handlers

### Vulnerable

```python
@app.errorhandler(Exception)
def handle_exception(e):
    return jsonify(error=str(e)), 500

@app.route('/data')
def get_data():
    try:
        return jsonify(fetch_data())
    except Exception as e:
        return jsonify(error=str(e)), 500
```

### Safe

```python
@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.exception("Unhandled exception")
    return jsonify(error="Internal server error"), 500

@app.route('/data')
def get_data():
    try:
        return jsonify(fetch_data())
    except Exception as e:
        app.logger.exception("Error fetching data")
        return jsonify(error="Internal server error"), 500
```

Log exceptions server-side using `app.logger.exception()`. Return a generic
message to the client without exposing exception details.

## FastAPI exception handlers

### Vulnerable

```python
@app.get("/data")
async def get_data():
    try:
        return fetch_data()
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"detail": str(exc)}
        )
```

### Safe

```python
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)

@app.get("/data")
async def get_data():
    try:
        return fetch_data()
    except Exception as exc:
        logger.exception("Error fetching data")
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )
```

Use `HTTPException` with a generic message. Log the full exception
server-side with the logging module. FastAPI's exception handlers
automatically serialize `detail` without exposing the full exception.

## FastAPI custom exception handlers

### Vulnerable

```python
from fastapi.exception_handlers import http_exception_handler

@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return JSONResponse(
        status_code=400,
        content={"error": str(exc)}
    )
```

### Safe

```python
from fastapi.responses import JSONResponse

@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    logger.exception("Validation error")
    return JSONResponse(
        status_code=400,
        content={"error": "Invalid input"}
    )
```

Return a generic message from custom exception handlers. Log the original
exception server-side for debugging.

## Bare exception handlers

### Vulnerable

```python
@app.route('/process', methods=['POST'])
def process():
    try:
        return process_request()
    except:
        import traceback
        return jsonify(error=traceback.format_exc()), 500
```

### Safe

```python
@app.route('/process', methods=['POST'])
def process():
    try:
        return process_request()
    except Exception as e:
        logger.exception("Error processing request")
        return jsonify(error="Internal server error"), 500
```

Catch specific exception types instead of bare `except`. Log the exception
server-side and return a generic error message to the client.
