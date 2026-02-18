from __future__ import annotations

import json
from datetime import datetime, timedelta

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.tool(name="getweatherforecast")
    def get_weather_forecast(location: str, days: int = 3) -> dict:
        """
        Get weather forecast for a specified location.
        
        Args:
            location: City name or location string (e.g., "Paris", "New York, NY")
            days: Number of days to forecast (default: 3, max: 7)
        
        Returns:
            A dictionary containing weather forecast with temperature, conditions, and alerts.
        """
        try:
            # Validate inputs
            if not location or not location.strip():
                return {
                    "summary": "Invalid location provided",
                    "result": None,
                    "next_actions": ["Please provide a valid location"],
                    "errors": ["Location cannot be empty"],
                }
            
            # Limit days to reasonable range
            if days < 1:
                days = 1
            elif days > 7:
                days = 7
            
            # Mock weather data (in a real implementation, this would call a weather API)
            # For demonstration purposes, we're generating sample forecast data
            forecast_data = []
            base_date = datetime.now()
            
            # Sample weather conditions
            conditions_list = [
                "Sunny", "Partly Cloudy", "Cloudy", "Light Rain", 
                "Rain", "Thunderstorms", "Snow", "Clear"
            ]
            
            for day_offset in range(days):
                forecast_date = base_date + timedelta(days=day_offset)
                day_name = forecast_date.strftime("%A")
                date_str = forecast_date.strftime("%Y-%m-%d")
                
                # Generate sample temperature (varying by day)
                base_temp = 20 + (day_offset % 5) * 2
                temp_high = base_temp + 5
                temp_low = base_temp - 3
                
                # Pick a condition (cycle through for variety)
                condition = conditions_list[day_offset % len(conditions_list)]
                
                forecast_data.append({
                    "date": date_str,
                    "day": day_name,
                    "temperature": {
                        "high": f"{temp_high}°C",
                        "low": f"{temp_low}°C",
                        "unit": "celsius",
                    },
                    "conditions": condition,
                    "precipitation_chance": f"{(day_offset * 15) % 100}%",
                    "humidity": f"{50 + (day_offset * 5) % 40}%",
                    "wind_speed": f"{10 + (day_offset * 3) % 20} km/h",
                })
            
            # Check for severe weather alerts (mock logic)
            alerts = []
            if any("Thunderstorms" in day["conditions"] or "Snow" in day["conditions"] 
                   for day in forecast_data):
                alerts.append({
                    "type": "weather_advisory",
                    "severity": "moderate",
                    "message": "Severe weather conditions expected in the forecast period",
                })
            
            result = {
                "location": location.strip(),
                "forecast_days": days,
                "forecast": forecast_data,
                "alerts": alerts if alerts else [],
                "timestamp": datetime.now().isoformat(),
                "note": "This is a mock weather service. For production use, integrate with a real weather API (e.g., OpenWeatherMap, Weather.gov)."
            }
            
            return {
                "summary": f"Weather forecast for {location} ({days} days)",
                "result": result,
                "next_actions": [
                    "Review forecast details",
                    "Check for weather alerts",
                ],
                "errors": [],
            }
        
        except Exception as e:
            return {
                "summary": "Error retrieving weather forecast",
                "result": None,
                "next_actions": ["Check location spelling", "Try again"],
                "errors": [f"Exception: {str(e)}"],
            }
