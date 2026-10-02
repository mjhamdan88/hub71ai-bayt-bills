from django.conf import settings
import base64
import uuid
import os


def decode_base64_media(base64_string, output_subdir="media", file_ext="jpg"):
    """
    Decodes a base64-encoded media file (image, audio, etc) and writes it into:
      <settings.MEDIA_ROOT>/<output_subdir>/<uuid>.<file_ext>
    Returns the *relative* path "media/<uuid>.<file_ext>" (i.e. no leading slash).
    
    So physically:   /my_project/media/media/<uuid>.<file_ext>
    DB storage:      "media/<uuid>.<file_ext>"
    Final serve URL: <MEDIA_URL>/media/<uuid>.<file_ext> => /media/media/<uuid>.<file_ext>
    """
    # 1) Physical directory
    physical_dir = os.path.join(settings.MEDIA_ROOT, output_subdir)
    os.makedirs(physical_dir, exist_ok=True)

    # 2) Generate filename
    filename = f"{uuid.uuid4()}.{file_ext}"
    full_path = os.path.join(physical_dir, filename)

    # 3) Write the file
    with open(full_path, "wb") as f:
        f.write(base64.b64decode(base64_string))

    # 4) Return the relative DB path: "media/<uuid>.<file_ext>"
    return os.path.join(output_subdir, filename)