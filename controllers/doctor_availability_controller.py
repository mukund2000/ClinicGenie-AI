from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from core.database import (
    search_doctors_by_date_range,
    search_doctor_availability_by_name_and_date_range,
)


router = APIRouter(tags=["doctor-availability"])


class DateRangeRequest(BaseModel):
    """Request model for date range queries"""
    start_date: str = Field(
        description="Start date in DD-MM-YYYY format",
        pattern=r"^\d{2}-\d{2}-\d{4}$"
    )
    end_date: str = Field(
        description="End date in DD-MM-YYYY format",
        pattern=r"^\d{2}-\d{2}-\d{4}$"
    )


class DoctorAvailabilityResponse(BaseModel):
    """Response model for doctor availability"""
    doctor_name: str
    specialization: str
    date_slot: str
    is_available: bool


@router.post(
    "/doctors/search-available",
    status_code=status.HTTP_200_OK,
    response_model=list[dict[str, Any]]
)
def search_available_doctors(
    payload: DateRangeRequest,
) -> list[dict[str, Any]]:
    """
    Search for all available doctors within a date range.
    
    Args:
        payload: DateRangeRequest containing start_date and end_date
        
    Returns:
        List of available appointment slots with doctor information
        
    Example:
        POST /doctors/search-available
        {
            "start_date": "15-05-2024",
            "end_date": "20-05-2024"
        }
    """
    try:
        results = search_doctors_by_date_range(
            start_date=payload.start_date,
            end_date=payload.end_date,
        )
        
        if not results:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No available doctors found between {payload.start_date} and {payload.end_date}",
            )
        
        return results
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error searching for available doctors: {str(e)}",
        ) from e


@router.get(
    "/doctors/{doctor_name}/search-available",
    status_code=status.HTTP_200_OK,
    response_model=list[dict[str, Any]]
)
def search_doctor_availability(
    doctor_name: str,
    start_date: str = Query(
        ...,
        description="Start date in DD-MM-YYYY format",
        pattern=r"^\d{2}-\d{2}-\d{4}$"
    ),
    end_date: str = Query(
        ...,
        description="End date in DD-MM-YYYY format",
        pattern=r"^\d{2}-\d{2}-\d{4}$"
    ),
) -> list[dict[str, Any]]:
    """
    Search for a specific doctor's availability within a date range.
    
    Args:
        doctor_name: Name of the doctor to search for
        start_date: Start date in DD-MM-YYYY format
        end_date: End date in DD-MM-YYYY format
        
    Returns:
        List of available appointment slots for the doctor
        
    Example:
        GET /doctors/john doe/search-available?start_date=15-05-2024&end_date=20-05-2024
    """
    try:
        results = search_doctor_availability_by_name_and_date_range(
            doctor_name=doctor_name,
            start_date=start_date,
            end_date=end_date,
        )
        
        if not results:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No available slots found for Dr. {doctor_name} between {start_date} and {end_date}",
            )
        
        return results
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error searching for doctor availability: {str(e)}",
        ) from e
