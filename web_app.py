import os
import shutil
import tempfile
from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse
import uvicorn

from core import convert_csv, convert_xml

app = FastAPI(
    title="CALM to AtoM Converter",
    description="Web wrapper for migrating CALM exports to AtoM.",
    version="1.0.0"
)

def cleanup_files(*file_paths):
    for fpath in file_paths:
        try:
            if os.path.exists(fpath):
                os.remove(fpath)
        except Exception:
            pass


def _pick_converter(filename: str):
    """Return (converter_callable, input_suffix) for the uploaded file.

    XML uploads (.xml or .dscribe) are routed to convert_xml; everything
    else goes to convert_csv, matching the CLI's --format auto behaviour.
    """
    lower = (filename or "").lower()
    if lower.endswith((".xml", ".dscribe")):
        return convert_xml, ".xml"
    return convert_csv, ".csv"


@app.post("/convert", response_class=FileResponse)
async def convert_file(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Upload a CALM CSV or DSCribe XML file and receive an AtoM-compatible CSV back.
    """
    converter, input_suffix = _pick_converter(file.filename)

    # Create temporary files for input and output
    fd_in, temp_input = tempfile.mkstemp(suffix=input_suffix)
    fd_out, temp_output = tempfile.mkstemp(suffix=".csv")

    os.close(fd_in)
    os.close(fd_out)

    try:
        # Save the uploaded file to the temporary input file
        with open(temp_input, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Convert! The converter callable has the same signature for both
        # CSV and XML, so the endpoint stays format-agnostic.
        converter(temp_input, temp_output)

        # Schedule cleanup after response is sent
        background_tasks.add_task(cleanup_files, temp_input, temp_output)

        # Return the converted file as a downloadable response
        return FileResponse(
            temp_output,
            media_type="text/csv",
            filename=f"atom_import_{file.filename}"
        )
    except Exception as e:
        # If an error happens before returning, clean up immediately
        cleanup_files(temp_input, temp_output)
        raise e

if __name__ == "__main__":
    uvicorn.run("web_app:app", host="0.0.0.0", port=8000, reload=True)