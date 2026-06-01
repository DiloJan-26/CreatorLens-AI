def calculate_engagement_rate(
    likes: int | None,
    comments: int | None,
    views: int | None,
) -> float | None:
    if views is None or views <= 0:
        return None

    if likes is None and comments is None:
        return None

    total_engagements = (likes or 0) + (comments or 0)
    return round((total_engagements / views) * 100, 4)
