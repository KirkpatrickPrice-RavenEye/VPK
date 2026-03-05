from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from uuid import UUID
import os

from app.core.database import get_db
from app.models.user import User
from app.services.job_service import JobService
from app.api.deps import get_current_active_user

router = APIRouter()


@router.get("/{job_id}/logs")
async def get_job_logs(
    job_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get job logs"""
    job_service = JobService(db)
    job = job_service.get_job(job_id, current_user)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.log_file_path:
        return {"logs": "No logs available yet"}

    try:
        import os

        print(f"DEBUG: job.log_file_path = '{job.log_file_path}'")
        print(
            f"DEBUG: os.path.exists(job.log_file_path) = {os.path.exists(job.log_file_path)}"
        )
        print(
            f"DEBUG: os.path.isdir(job.log_file_path) = {os.path.isdir(job.log_file_path)}"
        )
        print(
            f"DEBUG: os.path.isfile(job.log_file_path) = {os.path.isfile(job.log_file_path)}"
        )

        if os.path.isdir(job.log_file_path):
            # List contents
            try:
                contents = os.listdir(job.log_file_path)
                return {
                    "logs": f"Log file path is a directory, not a file. Contents: {contents}"
                }
            except:
                return {"logs": "Log file path is a directory, not a file"}
        elif not os.path.exists(job.log_file_path):
            return {"logs": "Log file not found"}
        else:
            with open(job.log_file_path, "r") as f:
                logs = f.read()
            return {"logs": logs}
    except FileNotFoundError:
        return {"logs": "Log file not found"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading logs: {str(e)}")


@router.get("/{job_id}/pot")
async def get_job_pot_file(
    job_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Download the pot file for a job"""
    job_service = JobService(db)
    job = job_service.get_job(job_id, current_user)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.pot_file_path:
        raise HTTPException(
            status_code=404,
            detail="No pot file available - job may not be completed or no passwords were cracked",
        )

    if not os.path.exists(job.pot_file_path):
        raise HTTPException(status_code=404, detail="Pot file not found on disk")

    if not os.path.isfile(job.pot_file_path):
        raise HTTPException(status_code=500, detail="Pot file path is not a file")

    # Return the file as a download
    filename = f"job_{job_id}_results.pot"
    return FileResponse(
        path=job.pot_file_path,
        filename=filename,
        media_type="text/plain",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Description": "Hashcat pot file containing cracked passwords",
        },
    )


@router.get("/{job_id}/pot/preview")
async def preview_job_pot_file(
    job_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Preview the contents of the pot file (first 50 lines)"""
    job_service = JobService(db)
    job = job_service.get_job(job_id, current_user)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.pot_file_path:
        return {
            "preview": "No pot file available - job may not be completed or no passwords were cracked"
        }

    try:
        if os.path.isdir(job.pot_file_path):
            return {"preview": "Pot file path is a directory, not a file"}
        elif not os.path.exists(job.pot_file_path):
            return {"preview": "Pot file not found"}
        else:
            with open(job.pot_file_path, "r") as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= 50:  # Limit to first 50 lines
                        lines.append(
                            "... (truncated, download full file for complete results)"
                        )
                        break
                    lines.append(line.rstrip())

                if not lines:
                    return {"preview": "Pot file is empty - no passwords were cracked"}

                return {
                    "preview": "\n".join(lines),
                    "total_lines_shown": len(lines)
                    - (1 if "truncated" in lines[-1] else 0),
                    "truncated": len(lines) == 51,  # 50 lines + truncation message
                }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading pot file: {str(e)}")
