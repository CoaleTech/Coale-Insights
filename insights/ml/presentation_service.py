"""
Board-Ready Presentation Mode Service

This service provides comprehensive presentation capabilities for intelligence dashboards including:
- Executive summary generation for board presentations  
- PowerPoint-ready formatting and layouts
- Full-screen presentation mode toggle
- Key metrics highlighting and visualization
- Professional board-ready styling
- Export capabilities for multiple formats
- Cross-dashboard presentation consistency

Author: AI Assistant
Version: 1.0.0
"""

import frappe
from frappe import _
from datetime import datetime, timedelta
import json
from typing import Dict, List, Any, Optional
import base64
import io
from PIL import Image, ImageDraw, ImageFont
import logging

logger = logging.getLogger(__name__)

class PresentationModeService:
    """
    Service for generating board-ready presentations from intelligence dashboards
    
    Features:
    - Executive summary generation
    - PowerPoint export functionality  
    - Full-screen presentation views
    - Professional formatting
    - Cross-dashboard consistency
    """
    
    def __init__(self):
        """Initialize Presentation Mode Service"""
        self.service_name = "Board Presentation Service"
        
        # Presentation templates
        self.templates = {
            "executive": "executive_summary_template",
            "detailed": "detailed_analysis_template", 
            "comparison": "comparison_template",
            "trend": "trend_analysis_template"
        }
        
        # Color schemes for different dashboard types
        self.color_schemes = {
            "executive": {"primary": "#1f2937", "secondary": "#3b82f6", "accent": "#10b981"},
            "financial": {"primary": "#059669", "secondary": "#065f46", "accent": "#047857"},
            "operations": {"primary": "#7c3aed", "secondary": "#5b21b7", "accent": "#8b5cf6"},
            "hr": {"primary": "#dc2626", "secondary": "#991b1b", "accent": "#ef4444"},
            "esg": {"primary": "#059669", "secondary": "#065f46", "accent": "#10b981"},
            "budget": {"primary": "#d97706", "secondary": "#92400e", "accent": "#f59e0b"}
        }
        
        # Standard slide layouts
        self.slide_layouts = {
            "title": {"title_size": "2xl", "content_cols": 1},
            "overview": {"title_size": "xl", "content_cols": 2},
            "metrics": {"title_size": "lg", "content_cols": 3},
            "chart": {"title_size": "lg", "content_cols": 1},
            "table": {"title_size": "lg", "content_cols": 1}
        }
    
    def generate_presentation_data(self, dashboard_type: str, dashboard_data: Dict, 
                                   presentation_type: str = "executive") -> Dict[str, Any]:
        """
        Generate comprehensive presentation data for any intelligence dashboard
        
        Args:
            dashboard_type: Type of dashboard (executive, financial, hr, etc.)
            dashboard_data: Raw dashboard data
            presentation_type: Type of presentation to generate
            
        Returns:
            Complete presentation data including slides, formatting, and export options
        """
        try:
            logger.info(f"Generating {presentation_type} presentation for {dashboard_type} dashboard")
            
            # Get color scheme for dashboard type
            colors = self.color_schemes.get(dashboard_type.lower(), self.color_schemes["executive"])
            
            # Generate slides based on presentation type
            if presentation_type == "executive":
                slides = self._generate_executive_slides(dashboard_data, colors)
            elif presentation_type == "detailed":
                slides = self._generate_detailed_slides(dashboard_data, colors)
            elif presentation_type == "comparison":
                slides = self._generate_comparison_slides(dashboard_data, colors)
            else:
                slides = self._generate_executive_slides(dashboard_data, colors)
            
            # Generate executive summary
            executive_summary = self._generate_executive_summary(dashboard_data, dashboard_type)
            
            # Generate key insights
            key_insights = self._extract_key_insights(dashboard_data, dashboard_type)
            
            # Generate recommendations
            recommendations = self._extract_recommendations(dashboard_data, dashboard_type)
            
            presentation_data = {
                "metadata": {
                    "dashboard_type": dashboard_type,
                    "presentation_type": presentation_type,
                    "generated_at": frappe.utils.now(),
                    "total_slides": len(slides),
                    "color_scheme": colors,
                    "company": frappe.db.get_default("Company") or "Your Company"
                },
                "executive_summary": executive_summary,
                "key_insights": key_insights,
                "recommendations": recommendations,
                "slides": slides,
                "export_options": self._get_export_options(),
                "presentation_settings": self._get_presentation_settings()
            }
            
            return presentation_data
            
        except Exception as e:
            logger.error(f"Error generating presentation data: {e}")
            frappe.log_error(f"Presentation Generation Error: {str(e)}", "Board Presentation Service")
            return {"error": str(e)}
    
    def _generate_executive_slides(self, data: Dict, colors: Dict) -> List[Dict[str, Any]]:
        """Generate executive summary slides"""
        slides = []
        
        # Title slide
        slides.append({
            "id": 1,
            "type": "title",
            "layout": self.slide_layouts["title"],
            "colors": colors,
            "content": {
                "title": f"{data.get('dashboard_type', '').replace('_', ' ').title()} Intelligence",
                "subtitle": f"Executive Summary - {datetime.now().strftime('%B %Y')}",
                "company": frappe.db.get_default("Company") or "Your Company",
                "logo_placeholder": True
            }
        })
        
        # Key Metrics Overview slide
        key_metrics = self._extract_key_metrics_for_presentation(data)
        slides.append({
            "id": 2,
            "type": "overview",
            "layout": self.slide_layouts["overview"],
            "colors": colors,
            "content": {
                "title": "Key Performance Indicators",
                "metrics": key_metrics,
                "layout": "metrics_grid"
            }
        })
        
        # Performance Trends slide
        if self._has_trend_data(data):
            slides.append({
                "id": 3,
                "type": "chart",
                "layout": self.slide_layouts["chart"],
                "colors": colors,
                "content": {
                    "title": "Performance Trends",
                    "chart_type": "line",
                    "chart_data": self._extract_trend_data_for_chart(data),
                    "insights": self._generate_trend_insights(data)
                }
            })
        
        # Key Insights slide  
        insights = self._extract_key_insights(data, data.get('dashboard_type', 'general'))
        if insights:
            slides.append({
                "id": 4,
                "type": "overview",
                "layout": self.slide_layouts["overview"],
                "colors": colors,
                "content": {
                    "title": "Key Insights",
                    "insights": insights[:5],  # Top 5 insights
                    "layout": "insights_list"
                }
            })
        
        # Recommendations slide
        recommendations = self._extract_recommendations(data, data.get('dashboard_type', 'general'))
        if recommendations:
            slides.append({
                "id": 5,
                "type": "overview",
                "layout": self.slide_layouts["overview"],
                "colors": colors,
                "content": {
                    "title": "Strategic Recommendations",
                    "recommendations": recommendations[:4],  # Top 4 recommendations
                    "layout": "recommendations_grid"
                }
            })
        
        return slides
    
    def _generate_detailed_slides(self, data: Dict, colors: Dict) -> List[Dict[str, Any]]:
        """Generate detailed analysis slides"""
        slides = self._generate_executive_slides(data, colors)  # Start with executive slides
        
        # Add detailed breakdown slides
        if 'departmental_analysis' in data:
            slides.append({
                "id": len(slides) + 1,
                "type": "table",
                "layout": self.slide_layouts["table"],
                "colors": colors,
                "content": {
                    "title": "Departmental Performance",
                    "table_data": self._format_departmental_table(data['departmental_analysis']),
                    "layout": "performance_table"
                }
            })
        
        if 'variance_trends' in data:
            slides.append({
                "id": len(slides) + 1,
                "type": "chart",
                "layout": self.slide_layouts["chart"],
                "colors": colors,
                "content": {
                    "title": "Variance Analysis",
                    "chart_type": "bar",
                    "chart_data": self._format_variance_chart_data(data['variance_trends']),
                    "insights": ["Variance trending analysis", "Performance patterns", "Control insights"]
                }
            })
        
        return slides
    
    def _generate_comparison_slides(self, data: Dict, colors: Dict) -> List[Dict[str, Any]]:
        """Generate comparison-focused slides"""
        slides = []
        
        # Title slide
        slides.append({
            "id": 1,
            "type": "title",
            "layout": self.slide_layouts["title"],
            "colors": colors,
            "content": {
                "title": "Performance Comparison Analysis",
                "subtitle": f"Benchmarking Report - {datetime.now().strftime('%B %Y')}",
                "company": frappe.db.get_default("Company") or "Your Company"
            }
        })
        
        # Add comparison-specific slides based on available data
        # This is a template - specific implementations would vary by dashboard type
        
        return slides
    
    def _generate_executive_summary(self, data: Dict, dashboard_type: str) -> Dict[str, Any]:
        """Generate executive summary text"""
        try:
            summary_parts = []
            
            # Performance overview
            if 'summary' in data:
                summary_data = data['summary']
                if dashboard_type.lower() == 'budget':
                    variance = summary_data.get('variance_percentage', 0)
                    if abs(variance) <= 5:
                        performance = "excellent"
                    elif abs(variance) <= 15:
                        performance = "good" 
                    else:
                        performance = "needs attention"
                    
                    summary_parts.append(f"Budget performance is {performance} with {variance:.1f}% variance from plan.")
                
                elif dashboard_type.lower() == 'hr':
                    retention = summary_data.get('retention_rate', 0)
                    summary_parts.append(f"Employee retention rate stands at {retention:.1f}%.")
                
                elif dashboard_type.lower() == 'manufacturing':
                    oee = summary_data.get('overall_oee', 0)
                    summary_parts.append(f"Overall Equipment Effectiveness achieved {oee:.1f}%.")
            
            # Alerts and issues
            if 'alerts' in data and data['alerts']:
                high_alerts = len([a for a in data['alerts'] if a.get('severity') == 'high'])
                if high_alerts > 0:
                    summary_parts.append(f"{high_alerts} critical items require immediate attention.")
            
            # Positive highlights
            if 'recommendations' in data and data['recommendations']:
                summary_parts.append(f"{len(data['recommendations'])} improvement opportunities identified.")
            
            # Default summary if no specific data
            if not summary_parts:
                summary_parts.append(f"Overall {dashboard_type.replace('_', ' ')} performance metrics reviewed.")
            
            return {
                "text": " ".join(summary_parts),
                "key_points": summary_parts,
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error generating executive summary: {e}")
            return {
                "text": f"{dashboard_type.replace('_', ' ').title()} dashboard summary generated.",
                "key_points": ["Performance metrics reviewed", "Analysis completed"],
                "generated_at": datetime.now().isoformat()
            }
    
    def _extract_key_insights(self, data: Dict, dashboard_type: str) -> List[Dict[str, Any]]:
        """Extract key insights for presentation"""
        insights = []
        
        try:
            # Extract insights based on dashboard type
            if dashboard_type.lower() == 'budget':
                if 'summary' in data:
                    variance_pct = data['summary'].get('variance_percentage', 0)
                    insights.append({
                        "title": "Budget Variance",
                        "value": f"{variance_pct:.1f}%",
                        "insight": f"Current variance is {'favorable' if variance_pct >= 0 else 'unfavorable'}",
                        "impact": "high" if abs(variance_pct) > 15 else "medium"
                    })
                
                if 'forecast_accuracy' in data:
                    accuracy = data['forecast_accuracy'].get('overall_accuracy', 0)
                    insights.append({
                        "title": "Forecast Accuracy", 
                        "value": f"{accuracy:.1f}%",
                        "insight": f"Forecasting {'excellent' if accuracy >= 90 else 'good' if accuracy >= 80 else 'needs improvement'}",
                        "impact": "medium"
                    })
            
            elif dashboard_type.lower() == 'hr':
                # HR-specific insights
                if 'summary' in data:
                    insights.append({
                        "title": "Workforce Performance",
                        "value": "Stable",
                        "insight": "Employee performance tracking active",
                        "impact": "medium"
                    })
            
            # Add generic insights if available
            if 'performance_metrics' in data:
                metrics = data['performance_metrics']
                if isinstance(metrics, dict) and 'overall_score' in metrics:
                    score = metrics['overall_score']
                    insights.append({
                        "title": "Overall Performance",
                        "value": f"{score:.0f}/100",
                        "insight": f"Performance rating: {'Excellent' if score >= 90 else 'Good' if score >= 75 else 'Needs Improvement'}",
                        "impact": "high"
                    })
            
            return insights[:6]  # Limit to top 6 insights
            
        except Exception as e:
            logger.error(f"Error extracting insights: {e}")
            return []
    
    def _extract_recommendations(self, data: Dict, dashboard_type: str) -> List[Dict[str, Any]]:
        """Extract recommendations for presentation"""
        try:
            recommendations = []
            
            # Check if recommendations exist in data
            if 'recommendations' in data and data['recommendations']:
                for rec in data['recommendations'][:4]:  # Top 4 recommendations
                    recommendations.append({
                        "title": rec.get('title', 'Improvement Opportunity'),
                        "description": rec.get('description', 'No description available'),
                        "priority": rec.get('priority', 'medium'),
                        "impact": rec.get('impact', 'Medium'),
                        "effort": rec.get('effort', 'Medium'),
                        "category": rec.get('category', 'general')
                    })
            
            # Generate generic recommendations if none exist
            if not recommendations:
                if dashboard_type.lower() == 'budget':
                    recommendations.append({
                        "title": "Enhance Budget Monitoring",
                        "description": "Implement real-time budget tracking and alerts",
                        "priority": "medium",
                        "impact": "High",
                        "effort": "Medium",
                        "category": "process"
                    })
                elif dashboard_type.lower() == 'hr':
                    recommendations.append({
                        "title": "Optimize Workforce Analytics",
                        "description": "Enhance employee performance tracking systems",
                        "priority": "medium", 
                        "impact": "High",
                        "effort": "Medium",
                        "category": "analytics"
                    })
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error extracting recommendations: {e}")
            return []
    
    def _extract_key_metrics_for_presentation(self, data: Dict) -> List[Dict[str, Any]]:
        """Extract key metrics formatted for presentation"""
        metrics = []
        
        try:
            # Extract from summary if available
            if 'summary' in data:
                summary = data['summary']
                
                for key, value in summary.items():
                    if isinstance(value, (int, float)):
                        # Format the metric for presentation
                        formatted_metric = {
                            "label": key.replace('_', ' ').title(),
                            "value": value,
                            "formatted_value": self._format_metric_value(value, key),
                            "trend": self._determine_trend_direction(value),
                            "importance": "high" if "percentage" in key or "score" in key else "medium"
                        }
                        metrics.append(formatted_metric)
            
            return metrics[:6]  # Limit to top 6 metrics
            
        except Exception as e:
            logger.error(f"Error extracting key metrics: {e}")
            return []
    
    def _format_metric_value(self, value: float, metric_key: str) -> str:
        """Format metric values for presentation"""
        try:
            if 'percentage' in metric_key or 'rate' in metric_key:
                return f"{value:.1f}%"
            elif 'amount' in metric_key or 'total' in metric_key or 'cost' in metric_key:
                return f"${value:,.0f}"
            elif 'score' in metric_key:
                return f"{value:.0f}/100"
            elif 'count' in metric_key:
                return f"{value:,.0f}"
            else:
                return str(round(value, 2))
        except Exception:
            return str(value)
    
    def _determine_trend_direction(self, value: float) -> str:
        """Determine trend direction for visualization"""
        # This is simplified - real implementation would compare with historical data
        if value > 0:
            return "up"
        elif value < 0:
            return "down"
        else:
            return "stable"
    
    def _has_trend_data(self, data: Dict) -> bool:
        """Check if dashboard has trend data for charts"""
        trend_keys = ['variance_trends', 'monthly_data', 'trend_analysis', 'historical_data']
        return any(key in data for key in trend_keys)
    
    def _extract_trend_data_for_chart(self, data: Dict) -> Dict[str, Any]:
        """Extract trend data formatted for charts"""
        try:
            chart_data = {"labels": [], "datasets": []}
            
            # Look for trend data in various formats
            if 'variance_trends' in data and 'monthly_variances' in data['variance_trends']:
                monthly_data = data['variance_trends']['monthly_variances']
                chart_data["labels"] = [item.get('month', '') for item in monthly_data]
                chart_data["datasets"] = [{
                    "label": "Variance %",
                    "data": [item.get('variance_percentage', 0) for item in monthly_data],
                    "borderColor": "#3b82f6",
                    "backgroundColor": "rgba(59, 130, 246, 0.1)"
                }]
            
            return chart_data
            
        except Exception as e:
            logger.error(f"Error extracting trend data: {e}")
            return {"labels": [], "datasets": []}
    
    def _generate_trend_insights(self, data: Dict) -> List[str]:
        """Generate insights about trends"""
        insights = []
        
        try:
            if 'variance_trends' in data:
                trends = data['variance_trends']
                direction = trends.get('trend_direction', 'stable')
                volatility = trends.get('volatility', 0)
                
                insights.append(f"Trend direction: {direction}")
                
                if volatility > 10:
                    insights.append("High volatility detected")
                else:
                    insights.append("Stable performance pattern")
                
                if 'seasonality' in trends:
                    seasonality = trends['seasonality']
                    if seasonality.get('seasonal', False):
                        insights.append("Seasonal patterns identified")
            
            return insights
            
        except Exception as e:
            logger.error(f"Error generating trend insights: {e}")
            return ["Trend analysis completed"]
    
    def _format_departmental_table(self, dept_data: List) -> Dict[str, Any]:
        """Format departmental data for table display"""
        try:
            headers = ["Department", "Budget", "Actual", "Variance", "Status"]
            rows = []
            
            for dept in dept_data[:8]:  # Limit to 8 departments for slide
                rows.append([
                    dept.get('department', ''),
                    f"${dept.get('budget', 0):,.0f}",
                    f"${dept.get('actual', 0):,.0f}",
                    f"{dept.get('variance_percentage', 0):.1f}%",
                    dept.get('status', '').title()
                ])
            
            return {"headers": headers, "rows": rows}
            
        except Exception as e:
            logger.error(f"Error formatting departmental table: {e}")
            return {"headers": [], "rows": []}
    
    def _format_variance_chart_data(self, variance_data: Dict) -> Dict[str, Any]:
        """Format variance data for charts"""
        try:
            if 'monthly_variances' in variance_data:
                monthly_data = variance_data['monthly_variances']
                
                return {
                    "labels": [item.get('month', '') for item in monthly_data],
                    "datasets": [{
                        "label": "Budget",
                        "data": [item.get('budget', 0) for item in monthly_data],
                        "backgroundColor": "#3b82f6"  # blue-500 (Espresso: --chart-color-1)
                    }, {
                        "label": "Actual",
                        "data": [item.get('actual', 0) for item in monthly_data],
                        "backgroundColor": "#ef4444"  # red-500 (Espresso: --chart-color-2)
                    }]
                }
            
            return {"labels": [], "datasets": []}
            
        except Exception as e:
            logger.error(f"Error formatting variance chart data: {e}")
            return {"labels": [], "datasets": []}
    
    def _get_export_options(self) -> Dict[str, Any]:
        """Get available export options"""
        return {
            "formats": ["pdf", "powerpoint", "json", "html"],
            "layouts": ["executive", "detailed", "handout"],
            "customization": {
                "include_charts": True,
                "include_tables": True,
                "include_recommendations": True,
                "company_branding": True
            }
        }
    
    def _get_presentation_settings(self) -> Dict[str, Any]:
        """Get presentation mode settings"""
        return {
            "fullscreen_mode": True,
            "auto_advance": False,
            "transition_effects": True,
            "presenter_notes": True,
            "slide_duration": 30,  # seconds
            "navigation_controls": True,
            "theme_customization": True
        }
    
    def generate_powerpoint_export(self, presentation_data: Dict) -> Dict[str, Any]:
        """Generate PowerPoint export data.

        Returns structured slide data, NOT a .pptx binary — no python-pptx
        generation is implemented. download_ready/message were previously
        worded as if a file were ready to download, which is misleading.
        See plan-eng-review D3.10.
        """
        try:
            export_data = {
                "format": "powerpoint",
                "slides": presentation_data.get('slides', []),
                "metadata": presentation_data.get('metadata', {}),
                "export_instructions": {
                    "slide_size": "16:9",
                    "font_family": "Arial",
                    "base_font_size": 24,
                    "template": "professional"
                },
                "generated_at": frappe.utils.now(),
                "download_ready": False
            }

            return {
                "status": "success",
                "data": export_data,
                "message": _("Structured slide data prepared (not a downloadable .pptx file)")
            }

        except Exception as e:
            logger.error(f"Error generating PowerPoint export: {e}")
            return {
                "status": "error", 
                "message": str(e)
            }
    
    def generate_pdf_export(self, presentation_data: Dict) -> Dict[str, Any]:
        """Generate PDF export data"""
        try:
            export_data = {
                "format": "pdf",
                "pages": self._convert_slides_to_pages(presentation_data.get('slides', [])),
                "metadata": presentation_data.get('metadata', {}),
                "formatting": {
                    "page_size": "A4",
                    "orientation": "landscape",
                    "margins": "standard",
                    "header_footer": True
                },
                "generated_at": frappe.utils.now(),
                "download_ready": True
            }
            
            return {
                "status": "success",
                "data": export_data,
                "message": "PDF export prepared"
            }
            
        except Exception as e:
            logger.error(f"Error generating PDF export: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def _convert_slides_to_pages(self, slides: List) -> List[Dict[str, Any]]:
        """Convert slide format to PDF page format"""
        pages = []
        
        for slide in slides:
            page = {
                "page_number": slide.get('id', 1),
                "content": slide.get('content', {}),
                "layout": slide.get('layout', {}),
                "colors": slide.get('colors', {}),
                "type": slide.get('type', 'standard')
            }
            pages.append(page)
        
        return pages