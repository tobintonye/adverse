from django.db import models, transaction
import uuid
from datetime import date, timedelta
from django.utils import timezone
from common.models import TimeStampedModel

"""  
# most billboard has 6 - 8 slots per loop
    Scheduling engine — decides what plays, when, and where.
    Key concepts:
  - A billboard runs a rotation loop (e.g. 10 x 30s ads = 5-minute loop)
  - TimeSlot  = one allocated play of one campaign's ad on one billboard on one date
  - Playlist  = all TimeSlots for a billboard on a given day, ordered by play_order
  - Capacity  = max plays/day = (operating_hours_seconds / media_duration_seconds)
  - Double-booking = total allocated slots/day exceeds billboard capacity
 
Flow triggered by campaign approval:
  manager_approve(campaign) → generate_schedule(campaign) → TimeSlot rows created
"""

class TimeSlot(TimeStampedModel):
     """
        One allocated play of a campaign's media on a specific billboard
        on a specific date at a specific position in the rotation.
    
        Created in bulk when a campaign is approved.
        Deleted when a campaign is cancelled or expired.
    """