# Python file upload patterns

Vulnerable-vs-safe snippets for the Python web frameworks the
`data_integrity.file_upload` scanner recognizes. When multiple safe forms
exist, the canonical one is shown first.

## Flask (werkzeug)

### Vulnerable

```python
@app.route('/upload', methods=['POST'])
def upload():
    file = request.files['file']
    file.save(os.path.join('uploads', file.filename))
    return 'Success'
```

### Safe

```python
from werkzeug.utils import secure_filename
import magic

ALLOWED_EXTENSIONS = {'txt', 'pdf', 'jpg', 'png', 'gif'}

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files['file']
    filename = secure_filename(file.filename)
    ext = filename.rsplit('.', 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        abort(400, 'File type not allowed')
    mime = magic.Magic(mime=True)
    file_content = file.read()
    if mime.from_buffer(file_content) not in {
        'image/jpeg', 'image/png', 'image/gif', 'text/plain',
        'application/pdf'
    }:
        abort(400, 'File content type not allowed')
    file_path = os.path.join('uploads', filename)
    with open(file_path, 'wb') as f:
        f.write(file_content)
    return 'Success'
```

`secure_filename` strips dangerous characters and prevents directory
traversal. Always check the extension against an allowlist and verify
magic bytes before saving.

## Django

### Vulnerable

```python
class ProfileForm(forms.Form):
    photo = forms.FileField()

def upload_photo(request):
    form = ProfileForm(request.POST, request.FILES)
    if form.is_valid():
        user = request.user
        user.photo = form.cleaned_data['photo']
        user.save()
```

### Safe

```python
from django.forms import FileField
from django.core.validators import FileExtensionValidator
import magic

ALLOWED_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif']
ALLOWED_MIMES = {'image/jpeg', 'image/png', 'image/gif'}

class ProfileForm(forms.Form):
    photo = FileField(
        validators=[
            FileExtensionValidator(
                allowed_extensions=ALLOWED_EXTENSIONS
            )
        ]
    )

def validate_photo_content(file_obj):
    mime = magic.Magic(mime=True)
    content = file_obj.read()
    file_obj.seek(0)
    if mime.from_buffer(content) not in ALLOWED_MIMES:
        raise forms.ValidationError("Invalid image type")

class ProfileForm(forms.Form):
    photo = FileField(validators=[validate_photo_content])

def upload_photo(request):
    form = ProfileForm(request.POST, request.FILES)
    if form.is_valid():
        user = request.user
        user.photo = form.cleaned_data['photo']
        user.save()
```

Use `FileExtensionValidator` on the form field. Always verify the file's
actual content type with `python-magic` rather than trusting the
Content-Type header sent by the client.

## FastAPI

### Vulnerable

```python
from fastapi import FastAPI, UploadFile, File
from pathlib import Path

app = FastAPI()

@app.post('/upload')
async def upload(file: UploadFile = File(...)):
    save_path = Path('uploads') / file.filename
    with open(save_path, 'wb') as f:
        content = await file.read()
        f.write(content)
    return {'filename': file.filename}
```

### Safe

```python
from fastapi import FastAPI, UploadFile, File, HTTPException
from pathlib import Path
import magic
import os

app = FastAPI()
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'jpg', 'png'}
ALLOWED_MIMES = {
    'image/jpeg', 'image/png', 'text/plain', 'application/pdf'
}

@app.post('/upload')
async def upload(file: UploadFile = File(...)):
    filename = file.filename
    if '.' not in filename:
        raise HTTPException(status_code=400, detail="No extension")
    ext = filename.rsplit('.', 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Type not allowed")

    content = await file.read()
    mime = magic.Magic(mime=True)
    actual_mime = mime.from_buffer(content)
    if actual_mime not in ALLOWED_MIMES:
        raise HTTPException(status_code=400, detail="Invalid content")

    safe_filename = os.path.basename(filename)
    save_path = Path('uploads') / safe_filename
    with open(save_path, 'wb') as f:
        f.write(content)
    return {'filename': safe_filename}
```

Always validate the extension against an allowlist before saving. Read the
entire file content and check its magic bytes with `python-magic` to
verify the actual type, not the provided extension or Content-Type header.
