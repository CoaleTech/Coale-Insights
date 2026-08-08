"""
ESG Intelligence Module

Provides comprehensive Environmental, Social, and Governance (ESG) analytics
for sustainability reporting and corporate responsibility tracking.
"""

import frappe
from frappe.utils import nowdate, add_months, add_days, flt, cint, date_diff, today
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import logging
from insights.cache_management.cache_manager import CacheManager

logger = logging.getLogger(__name__)


class ESGIntelligence:
    """
    ESG Intelligence system providing sustainability metrics, environmental impact tracking,
    social responsibility indicators, and governance compliance analytics.
    """
    
    def __init__(self):
        self.cache_manager = CacheManager()
        self.today = nowdate()
        
    def get_esg_overview(self, period: str = "YTD") -> Dict[str, Any]:
        """Get comprehensive ESG overview with environmental, social, and governance metrics"""
        try:
            cache_key = f"esg_overview_{period}"
            cached_result = self.cache_manager.get_cached_result(cache_key)
            if cached_result:
                return cached_result
            
            logger.info(f"Generating ESG overview for period: {period}")
            
            # Get date range
            date_condition = self._get_date_condition(period)
            
            # Aggregate ESG data
            esg_data = {
                # Environmental metrics
                "environmental_metrics": self._get_environmental_metrics(date_condition),
                
                # Social metrics
                "social_metrics": self._get_social_metrics(date_condition),
                
                # Governance metrics
                "governance_metrics": self._get_governance_metrics(date_condition),
                
                # ESG scoring
                "esg_score": self._calculate_esg_score(date_condition),
                
                # Sustainability targets
                "sustainability_targets": self._get_sustainability_targets(date_condition),
                
                # Carbon footprint
                "carbon_footprint": self._calculate_carbon_footprint(date_condition),
                
                # Compliance tracking
                "compliance_tracking": self._get_compliance_status(date_condition),
                
                # Stakeholder engagement
                "stakeholder_engagement": self._get_stakeholder_metrics(date_condition),
                
                # ESG benchmarking
                "industry_benchmarks": self._get_industry_benchmarks(),
                
                # Risk assessment
                "esg_risks": self._assess_esg_risks(date_condition),
                
                # Progress tracking
                "progress_tracking": self._track_esg_progress(date_condition),
                
                # Reporting readiness
                "reporting_readiness": self._assess_reporting_readiness(date_condition)
            }
            
            # Add metadata
            esg_data.update({
                "generated_at": datetime.now().isoformat(),
                "period": period,
                "currency": frappe.defaults.get_global_default("currency") or "USD"
            })
            
            # Cache result
            self.cache_manager.set_cached_result(cache_key, esg_data, expire_time=3600)
            
            return esg_data
            
        except Exception as e:
            logger.error(f"Error generating ESG overview: {e}")
            return {"error": str(e), "period": period}
    
    def _get_environmental_metrics(self, date_condition: str) -> Dict[str, Any]:
        """Calculate environmental impact metrics"""
        try:
            logger.info("Calculating environmental metrics...")
            
            # Energy consumption tracking
            energy_data = self._get_energy_consumption(date_condition)
            
            # Waste management metrics
            waste_data = self._get_waste_metrics(date_condition)
            
            # Water usage tracking
            water_data = self._get_water_usage(date_condition)
            
            # Emissions tracking
            emissions_data = self._get_emissions_tracking(date_condition)
            
            # Resource efficiency
            resource_efficiency = self._calculate_resource_efficiency(date_condition)
            
            # Green initiatives
            green_initiatives = self._track_green_initiatives(date_condition)
            
            environmental_score = self._calculate_environmental_score({
                "energy": energy_data,
                "waste": waste_data,
                "water": water_data,
                "emissions": emissions_data,
                "efficiency": resource_efficiency
            })
            
            return {
                "energy_consumption": energy_data,
                "waste_management": waste_data,
                "water_usage": water_data,
                "emissions": emissions_data,
                "resource_efficiency": resource_efficiency,
                "green_initiatives": green_initiatives,
                "environmental_score": environmental_score,
                "trends": self._calculate_environmental_trends(date_condition)
            }
            
        except Exception as e:
            logger.error(f"Error calculating environmental metrics: {e}")
            return {}
    
    def _get_social_metrics(self, date_condition: str) -> Dict[str, Any]:
        """Calculate social responsibility metrics"""
        try:
            logger.info("Calculating social responsibility metrics...")
            
            # Employee wellbeing
            employee_wellbeing = self._get_employee_wellbeing(date_condition)
            
            # Diversity and inclusion
            diversity_metrics = self._get_diversity_metrics(date_condition)
            
            # Community involvement
            community_metrics = self._get_community_involvement(date_condition)
            
            # Health and safety
            safety_metrics = self._get_health_safety_metrics(date_condition)
            
            # Training and development
            development_metrics = self._get_training_metrics(date_condition)
            
            # Customer satisfaction
            customer_metrics = self._get_customer_social_metrics(date_condition)
            
            # Supply chain responsibility
            supply_chain_social = self._get_supply_chain_social_metrics(date_condition)
            
            social_score = self._calculate_social_score({
                "employee_wellbeing": employee_wellbeing,
                "diversity": diversity_metrics,
                "community": community_metrics,
                "safety": safety_metrics,
                "development": development_metrics,
                "customers": customer_metrics
            })
            
            return {
                "employee_wellbeing": employee_wellbeing,
                "diversity_inclusion": diversity_metrics,
                "community_involvement": community_metrics,
                "health_safety": safety_metrics,
                "training_development": development_metrics,
                "customer_satisfaction": customer_metrics,
                "supply_chain_social": supply_chain_social,
                "social_score": social_score,
                "trends": self._calculate_social_trends(date_condition)
            }
            
        except Exception as e:
            logger.error(f"Error calculating social metrics: {e}")
            return {}
    
    def _get_governance_metrics(self, date_condition: str) -> Dict[str, Any]:
        """Calculate governance and compliance metrics"""
        try:
            logger.info("Calculating governance metrics...")
            
            # Board composition
            board_metrics = self._get_board_composition()
            
            # Ethics and compliance
            ethics_metrics = self._get_ethics_compliance(date_condition)
            
            # Risk management
            risk_management = self._get_risk_management_metrics(date_condition)
            
            # Transparency metrics
            transparency_metrics = self._get_transparency_metrics(date_condition)
            
            # Audit and controls
            audit_metrics = self._get_audit_metrics(date_condition)
            
            # Stakeholder rights
            stakeholder_rights = self._get_stakeholder_rights_metrics(date_condition)
            
            governance_score = self._calculate_governance_score({
                "board": board_metrics,
                "ethics": ethics_metrics,
                "risk": risk_management,
                "transparency": transparency_metrics,
                "audit": audit_metrics
            })
            
            return {
                "board_composition": board_metrics,
                "ethics_compliance": ethics_metrics,
                "risk_management": risk_management,
                "transparency": transparency_metrics,
                "audit_controls": audit_metrics,
                "stakeholder_rights": stakeholder_rights,
                "governance_score": governance_score,
                "trends": self._calculate_governance_trends(date_condition)
            }
            
        except Exception as e:
            logger.error(f"Error calculating governance metrics: {e}")
            return {}
    
    def _calculate_esg_score(self, date_condition: str) -> Dict[str, Any]:
        """Calculate overall ESG score"""
        try:
            logger.info("Calculating overall ESG score...")
            
            # Get component scores
            env_metrics = self._get_environmental_metrics(date_condition)
            social_metrics = self._get_social_metrics(date_condition)
            gov_metrics = self._get_governance_metrics(date_condition)
            
            env_score = env_metrics.get("environmental_score", {}).get("overall_score", 0)
            social_score = social_metrics.get("social_score", {}).get("overall_score", 0)
            governance_score = gov_metrics.get("governance_score", {}).get("overall_score", 0)
            
            # Calculate weighted overall score
            overall_score = (env_score * 0.35) + (social_score * 0.35) + (governance_score * 0.30)
            
            # Determine rating
            rating = self._get_esg_rating(overall_score)
            
            # Calculate improvement trajectory
            improvement_trajectory = self._calculate_improvement_trajectory(date_condition)
            
            return {
                "overall_score": round(overall_score, 1),
                "environmental_score": env_score,
                "social_score": social_score,
                "governance_score": governance_score,
                "rating": rating,
                "rating_description": self._get_rating_description(rating),
                "improvement_trajectory": improvement_trajectory,
                "benchmark_comparison": self._compare_to_industry_benchmark(overall_score),
                "score_breakdown": {
                    "environmental_weight": 35,
                    "social_weight": 35,
                    "governance_weight": 30
                }
            }
            
        except Exception as e:
            logger.error(f"Error calculating ESG score: {e}")
            return {"overall_score": 0}
    
    def _get_energy_consumption(self, date_condition: str) -> Dict[str, Any]:
        """Track energy consumption metrics"""
        try:
            # This would typically pull from utility data or energy management systems
            # For demo purposes, calculating based on operational data
            
            # Energy from operations (estimated from manufacturing data)
            energy_intensity = frappe.db.sql(f"""
                SELECT 
                    COUNT(*) as total_operations,
                    SUM(COALESCE(produced_qty, 0)) as total_production,
                    AVG(COALESCE(actual_operating_cost, 0)) as avg_cost
                FROM `tabWork Order` 
                WHERE docstatus = 1 {date_condition}
            """, as_dict=1)
            
            base_data = energy_intensity[0] if energy_intensity else {}
            total_production = base_data.get("total_production", 0) or 1
            
            # Estimated energy metrics (would be real data in production)
            energy_data = {
                "total_consumption_kwh": total_production * 2.5,  # Estimated 2.5 kWh per unit
                "renewable_energy_pct": 25,  # Example: 25% renewable
                "energy_intensity": 2.5,  # kWh per unit produced
                "energy_cost": total_production * 0.12,  # $0.12 per kWh
                "renewable_target": 50,  # Target: 50% renewable by target date
                "energy_efficiency_improvement": 5.2,  # 5.2% improvement YoY
                "carbon_intensity": total_production * 0.45  # kg CO2 per kWh
            }
            
            return energy_data
            
        except Exception as e:
            logger.error(f"Error calculating energy consumption: {e}")
            return {"total_consumption_kwh": 0}
    
    def _get_waste_metrics(self, date_condition: str) -> Dict[str, Any]:
        """Track waste management metrics"""
        try:
            # Calculate waste metrics from operational data
            production_data = frappe.db.sql(f"""
                SELECT 
                    SUM(COALESCE(produced_qty, 0)) as total_production,
                    AVG(COALESCE(actual_operating_cost, 0)) as avg_cost
                FROM `tabWork Order` 
                WHERE docstatus = 1 {date_condition}
            """, as_dict=1)
            
            base_data = production_data[0] if production_data else {}
            total_production = base_data.get("total_production", 0) or 1
            
            return {
                "total_waste_generated_kg": total_production * 0.1,  # 0.1 kg waste per unit
                "recycled_waste_pct": 65,  # 65% recycled
                "hazardous_waste_kg": total_production * 0.01,  # 0.01 kg hazardous per unit
                "waste_diverted_from_landfill_pct": 78,  # 78% diverted
                "waste_reduction_target": 20,  # 20% reduction target
                "circular_economy_initiatives": 8,  # Number of initiatives
                "waste_cost_per_unit": 0.05  # $0.05 waste cost per unit
            }
            
        except Exception as e:
            logger.error(f"Error calculating waste metrics: {e}")
            return {"total_waste_generated_kg": 0}
    
    def _get_water_usage(self, date_condition: str) -> Dict[str, Any]:
        """Track water usage and conservation metrics"""
        try:
            # Estimate water usage from operations
            operations = frappe.db.count("Work Order", filters={"docstatus": 1})
            
            return {
                "total_water_consumption_liters": operations * 50,  # 50L per operation
                "water_recycled_pct": 40,  # 40% water recycled
                "water_intensity": 50,  # Liters per unit
                "water_conservation_target": 30,  # 30% reduction target
                "wastewater_treatment_pct": 95,  # 95% treated
                "water_quality_compliance": 98,  # 98% compliance rate
                "rainwater_harvested_liters": operations * 10  # 10L rainwater per operation
            }
            
        except Exception as e:
            logger.error(f"Error calculating water usage: {e}")
            return {"total_water_consumption_liters": 0}
    
    def _get_emissions_tracking(self, date_condition: str) -> Dict[str, Any]:
        """Track greenhouse gas emissions"""
        try:
            # Calculate emissions from various sources
            
            # Transportation emissions (from deliveries)
            delivery_data = frappe.db.sql(f"""
                SELECT COUNT(*) as delivery_count
                FROM `tabDelivery Note`
                WHERE docstatus = 1 {date_condition}
            """, as_dict=1)
            
            deliveries = delivery_data[0].get("delivery_count", 0) if delivery_data else 0
            
            # Production emissions
            production_data = frappe.db.sql(f"""
                SELECT SUM(COALESCE(produced_qty, 0)) as total_production
                FROM `tabWork Order`
                WHERE docstatus = 1 {date_condition}
            """, as_dict=1)
            
            production = production_data[0].get("total_production", 0) if production_data else 0
            
            return {
                "scope_1_emissions_tco2": (production * 0.5) / 1000,  # Direct emissions
                "scope_2_emissions_tco2": (production * 0.3) / 1000,  # Electricity
                "scope_3_emissions_tco2": (deliveries * 25) / 1000,  # Value chain
                "total_emissions_tco2": ((production * 0.8) + (deliveries * 25)) / 1000,
                "emissions_intensity": 0.8,  # kg CO2 per unit
                "carbon_neutral_target_year": 2030,
                "emissions_reduction_pct": 12,  # 12% reduction YoY
                "carbon_offset_purchased_tco2": 50,  # 50 tCO2 offsets
                "net_emissions_tco2": ((production * 0.8) + (deliveries * 25) - 50000) / 1000
            }
            
        except Exception as e:
            logger.error(f"Error calculating emissions: {e}")
            return {"total_emissions_tco2": 0}
    
    def _calculate_resource_efficiency(self, date_condition: str) -> Dict[str, Any]:
        """Calculate resource efficiency metrics"""
        try:
            # Resource utilization from manufacturing
            efficiency_data = frappe.db.sql(f"""
                SELECT 
                    AVG(COALESCE(produced_qty, 0) / NULLIF(qty, 0)) as production_efficiency,
                    COUNT(*) as total_orders
                FROM `tabWork Order`
                WHERE docstatus = 1 {date_condition}
            """, as_dict=1)
            
            base_data = efficiency_data[0] if efficiency_data else {}
            production_eff = base_data.get("production_efficiency", 0) or 0.85
            
            return {
                "material_efficiency_pct": min(production_eff * 100, 100),
                "energy_efficiency_improvement_pct": 8.5,  # Year-over-year improvement
                "water_efficiency_improvement_pct": 6.2,
                "waste_reduction_achieved_pct": 15.3,
                "resource_recovery_rate_pct": 72,
                "circular_economy_score": 68,  # Out of 100
                "sustainable_sourcing_pct": 45  # % of materials from sustainable sources
            }
            
        except Exception as e:
            logger.error(f"Error calculating resource efficiency: {e}")
            return {"material_efficiency_pct": 0}
    
    def _track_green_initiatives(self, date_condition: str) -> List[Dict[str, Any]]:
        """Track green/sustainability initiatives"""
        try:
            # This would typically come from a sustainability projects tracking system
            # For demo purposes, creating sample initiatives
            
            initiatives = [
                {
                    "name": "Solar Panel Installation",
                    "status": "In Progress",
                    "progress_pct": 75,
                    "target_completion": "2026-06-30",
                    "expected_impact": "25% renewable energy increase",
                    "investment": 150000,
                    "category": "Energy"
                },
                {
                    "name": "Waste Reduction Program",
                    "status": "Completed",
                    "progress_pct": 100,
                    "target_completion": "2025-12-31",
                    "expected_impact": "30% waste reduction",
                    "investment": 25000,
                    "category": "Waste"
                },
                {
                    "name": "Water Conservation System",
                    "status": "Planning",
                    "progress_pct": 20,
                    "target_completion": "2026-12-31",
                    "expected_impact": "40% water usage reduction",
                    "investment": 80000,
                    "category": "Water"
                },
                {
                    "name": "Electric Vehicle Fleet",
                    "status": "In Progress",
                    "progress_pct": 45,
                    "target_completion": "2026-09-30",
                    "expected_impact": "60% transport emissions reduction",
                    "investment": 200000,
                    "category": "Transportation"
                }
            ]
            
            return initiatives
            
        except Exception as e:
            logger.error(f"Error tracking green initiatives: {e}")
            return []
    
    def _get_employee_wellbeing(self, date_condition: str) -> Dict[str, Any]:
        """Calculate employee wellbeing metrics"""
        try:
            # Employee engagement and wellbeing
            employee_data = frappe.db.sql(f"""
                SELECT 
                    COUNT(*) as total_employees,
                    SUM(CASE WHEN status = 'Active' THEN 1 ELSE 0 END) as active_employees
                FROM `tabEmployee`
                WHERE creation {date_condition.replace('posting_date', 'creation') if date_condition else ''}
            """, as_dict=1)
            
            base_data = employee_data[0] if employee_data else {}
            total_employees = base_data.get("total_employees", 0) or 100
            
            # Leave and attendance data
            leave_data = frappe.db.sql(f"""
                SELECT 
                    COUNT(*) as total_leaves,
                    AVG(total_leave_days) as avg_leave_days
                FROM `tabLeave Application`
                WHERE docstatus = 1 {date_condition.replace('posting_date', 'from_date') if date_condition else ''}
            """, as_dict=1)
            
            total_leaves = leave_data[0].get("total_leaves", 0) if leave_data else 0
            
            return {
                "employee_satisfaction_score": 4.2,  # Out of 5
                "work_life_balance_score": 3.8,  # Out of 5
                "mental_health_support_participation": 68,  # % participation
                "wellness_program_enrollment": 72,  # % enrolled
                "stress_level_index": 2.8,  # Out of 5 (lower is better)
                "flexible_work_adoption": 85,  # % using flexible options
                "employee_recognition_programs": 5,  # Number of programs
                "average_leave_utilization": min((total_leaves / max(total_employees, 1)) * 100, 100),
                "workplace_safety_incidents": max(0, total_employees // 50),  # Estimated incidents
                "health_insurance_coverage": 95  # % coverage
            }
            
        except Exception as e:
            logger.error(f"Error calculating employee wellbeing: {e}")
            return {"employee_satisfaction_score": 0}
    
    def _get_diversity_metrics(self, date_condition: str) -> Dict[str, Any]:
        """Calculate diversity and inclusion metrics"""
        try:
            # Gender diversity
            gender_data = frappe.db.sql(f"""
                SELECT 
                    gender,
                    COUNT(*) as count
                FROM `tabEmployee`
                WHERE status = 'Active'
                GROUP BY gender
            """, as_dict=1)
            
            total_employees = sum(row["count"] for row in gender_data)
            gender_distribution = {row["gender"] or "Not Specified": 
                                 round((row["count"] / max(total_employees, 1)) * 100, 1) 
                                 for row in gender_data}
            
            # Department diversity (using department as proxy for function)
            dept_data = frappe.db.sql("""
                SELECT 
                    department,
                    COUNT(*) as count
                FROM `tabEmployee`
                WHERE status = 'Active' AND department IS NOT NULL
                GROUP BY department
            """, as_dict=1)
            
            return {
                "gender_distribution": gender_distribution,
                "female_leadership_pct": gender_distribution.get("Female", 0) * 0.7,  # Estimated leadership %
                "pay_equity_ratio": 0.96,  # Pay ratio (female to male)
                "diverse_hiring_pct": 35,  # % of diverse hires
                "inclusion_index": 7.2,  # Out of 10
                "mentorship_programs": 3,  # Number of programs
                "diversity_training_completion": 88,  # % completion
                "employee_resource_groups": 4,  # Number of groups
                "accessibility_compliance": 92,  # % compliance
                "age_diversity_score": 6.8  # Out of 10
            }
            
        except Exception as e:
            logger.error(f"Error calculating diversity metrics: {e}")
            return {"gender_distribution": {}}
    
    def _get_community_involvement(self, date_condition: str) -> Dict[str, Any]:
        """Calculate community involvement metrics"""
        try:
            # Community engagement would typically come from dedicated tracking
            # For demo purposes, estimating based on company size
            
            employee_count = frappe.db.count("Employee", filters={"status": "Active"})
            
            return {
                "volunteer_participation_pct": 42,  # % of employees volunteering
                "community_investment": employee_count * 500,  # $500 per employee annually
                "local_supplier_spend_pct": 35,  # % of spend with local suppliers
                "community_partnerships": 8,  # Number of partnerships
                "charitable_donations": employee_count * 200,  # $200 per employee
                "skills_based_volunteering_hours": employee_count * 12,  # 12 hours per employee
                "educational_programs_supported": 5,  # Number of programs
                "local_employment_pct": 78,  # % of local hires
                "community_feedback_score": 4.1,  # Out of 5
                "social_impact_projects": 6  # Number of active projects
            }
            
        except Exception as e:
            logger.error(f"Error calculating community involvement: {e}")
            return {"volunteer_participation_pct": 0}
    
    def _get_health_safety_metrics(self, date_condition: str) -> Dict[str, Any]:
        """Calculate health and safety metrics"""
        try:
            employee_count = frappe.db.count("Employee", filters={"status": "Active"})
            
            return {
                "lost_time_injury_rate": max(0, (employee_count // 200)),  # Per 200,000 hours
                "total_recordable_incident_rate": max(0, (employee_count // 100)),
                "safety_training_completion_pct": 96,  # % completion
                "near_miss_reporting_rate": 15,  # Reports per 100 employees
                "workplace_inspection_score": 8.7,  # Out of 10
                "emergency_drill_compliance": 98,  # % compliance
                "occupational_health_program_participation": 85,  # % participation
                "safety_improvement_initiatives": 12,  # Number of initiatives
                "workers_compensation_claims": max(0, employee_count // 150),  # Estimated claims
                "safety_culture_index": 8.4  # Out of 10
            }
            
        except Exception as e:
            logger.error(f"Error calculating health and safety metrics: {e}")
            return {"lost_time_injury_rate": 0}
    
    def _get_training_metrics(self, date_condition: str) -> Dict[str, Any]:
        """Calculate training and development metrics"""
        try:
            employee_count = frappe.db.count("Employee", filters={"status": "Active"})
            
            return {
                "training_hours_per_employee": 32,  # Annual hours
                "skill_development_program_participation": 74,  # % participation
                "digital_literacy_training_completion": 82,  # % completion
                "leadership_development_participants": employee_count // 10,  # 10% in leadership programs
                "internal_promotion_rate": 68,  # % of roles filled internally
                "learning_budget_per_employee": 1200,  # Annual budget
                "professional_certification_support": 45,  # % receiving support
                "cross_functional_training_participation": 38,  # % participation
                "mentoring_program_participation": 28,  # % participation
                "knowledge_sharing_sessions": 24  # Sessions per year
            }
            
        except Exception as e:
            logger.error(f"Error calculating training metrics: {e}")
            return {"training_hours_per_employee": 0}
    
    def _get_customer_social_metrics(self, date_condition: str) -> Dict[str, Any]:
        """Calculate customer-related social metrics"""
        try:
            customer_count = frappe.db.count("Customer", filters={"disabled": 0})
            
            return {
                "customer_satisfaction_score": 4.3,  # Out of 5
                "product_safety_compliance": 98,  # % compliance
                "data_privacy_compliance": 96,  # % compliance
                "accessibility_features": 85,  # % of products with accessibility
                "customer_complaint_resolution_time": 2.5,  # Average days
                "fair_pricing_practices_score": 8.1,  # Out of 10
                "customer_education_programs": 8,  # Number of programs
                "responsible_marketing_compliance": 94,  # % compliance
                "customer_feedback_response_rate": 87,  # % of feedback addressed
                "inclusive_product_design": 72  # % of products designed inclusively
            }
            
        except Exception as e:
            logger.error(f"Error calculating customer social metrics: {e}")
            return {"customer_satisfaction_score": 0}
    
    def _get_supply_chain_social_metrics(self, date_condition: str) -> Dict[str, Any]:
        """Calculate supply chain social responsibility metrics"""
        try:
            supplier_count = frappe.db.count("Supplier")
            
            return {
                "supplier_code_of_conduct_compliance": 78,  # % compliance
                "ethical_sourcing_pct": 68,  # % ethical sourcing
                "supplier_labor_standards_audits": supplier_count // 5,  # 20% audited annually
                "fair_trade_certified_products_pct": 25,  # % fair trade
                "supplier_diversity_spend_pct": 18,  # % spend with diverse suppliers
                "supply_chain_transparency_score": 7.2,  # Out of 10
                "supplier_sustainability_training": 45,  # % trained
                "conflict_mineral_compliance": 92,  # % compliance
                "living_wage_supplier_compliance": 56,  # % paying living wages
                "supply_chain_risk_assessments": 4  # Annual assessments
            }
            
        except Exception as e:
            logger.error(f"Error calculating supply chain social metrics: {e}")
            return {"supplier_code_of_conduct_compliance": 0}
    
    def _calculate_environmental_score(self, env_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate environmental performance score"""
        try:
            # Score components (0-100 scale)
            energy_score = min(100, env_data.get("energy", {}).get("renewable_energy_pct", 0) * 2)
            waste_score = env_data.get("waste", {}).get("recycled_waste_pct", 0)
            water_score = env_data.get("water", {}).get("water_recycled_pct", 0) * 1.5
            emissions_score = max(0, 100 - (env_data.get("emissions", {}).get("emissions_intensity", 1) * 50))
            efficiency_score = env_data.get("efficiency", {}).get("material_efficiency_pct", 0)
            
            # Calculate weighted average
            overall_score = (energy_score * 0.25 + waste_score * 0.20 + water_score * 0.15 + 
                           emissions_score * 0.30 + efficiency_score * 0.10)
            
            return {
                "overall_score": round(overall_score, 1),
                "energy_score": round(energy_score, 1),
                "waste_score": round(waste_score, 1),
                "water_score": round(water_score, 1),
                "emissions_score": round(emissions_score, 1),
                "efficiency_score": round(efficiency_score, 1),
                "rating": self._get_score_rating(overall_score)
            }
            
        except Exception as e:
            logger.error(f"Error calculating environmental score: {e}")
            return {"overall_score": 0}
    
    def _calculate_social_score(self, social_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate social responsibility score"""
        try:
            # Score components (0-100 scale)
            wellbeing_score = social_data.get("employee_wellbeing", {}).get("employee_satisfaction_score", 0) * 20
            diversity_score = min(100, social_data.get("diversity", {}).get("inclusion_index", 0) * 10)
            community_score = social_data.get("community", {}).get("volunteer_participation_pct", 0) * 1.5
            safety_score = social_data.get("safety", {}).get("safety_culture_index", 0) * 10
            development_score = min(100, social_data.get("development", {}).get("skill_development_program_participation", 0))
            customer_score = social_data.get("customers", {}).get("customer_satisfaction_score", 0) * 20
            
            # Calculate weighted average
            overall_score = (wellbeing_score * 0.20 + diversity_score * 0.20 + community_score * 0.15 + 
                           safety_score * 0.20 + development_score * 0.15 + customer_score * 0.10)
            
            return {
                "overall_score": round(overall_score, 1),
                "wellbeing_score": round(wellbeing_score, 1),
                "diversity_score": round(diversity_score, 1),
                "community_score": round(community_score, 1),
                "safety_score": round(safety_score, 1),
                "development_score": round(development_score, 1),
                "customer_score": round(customer_score, 1),
                "rating": self._get_score_rating(overall_score)
            }
            
        except Exception as e:
            logger.error(f"Error calculating social score: {e}")
            return {"overall_score": 0}
    
    def _calculate_governance_score(self, gov_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate governance performance score"""
        try:
            # Score components (0-100 scale)
            board_score = 75  # Placeholder board composition score
            ethics_score = 85  # Placeholder ethics compliance score
            risk_score = 80  # Placeholder risk management score
            transparency_score = 78  # Placeholder transparency score
            audit_score = 88  # Placeholder audit & controls score
            
            # Calculate weighted average
            overall_score = (board_score * 0.25 + ethics_score * 0.25 + risk_score * 0.20 + 
                           transparency_score * 0.15 + audit_score * 0.15)
            
            return {
                "overall_score": round(overall_score, 1),
                "board_score": board_score,
                "ethics_score": ethics_score,
                "risk_score": risk_score,
                "transparency_score": transparency_score,
                "audit_score": audit_score,
                "rating": self._get_score_rating(overall_score)
            }
            
        except Exception as e:
            logger.error(f"Error calculating governance score: {e}")
            return {"overall_score": 0}
    
    def _get_esg_rating(self, score: float) -> str:
        """Convert ESG score to letter rating"""
        if score >= 85:
            return "AAA"
        elif score >= 80:
            return "AA"
        elif score >= 75:
            return "A"
        elif score >= 70:
            return "BBB"
        elif score >= 65:
            return "BB"
        elif score >= 60:
            return "B"
        elif score >= 55:
            return "CCC"
        else:
            return "C"
    
    def _get_score_rating(self, score: float) -> str:
        """Convert score to performance rating"""
        if score >= 90:
            return "Excellent"
        elif score >= 80:
            return "Good"
        elif score >= 70:
            return "Fair"
        elif score >= 60:
            return "Needs Improvement"
        else:
            return "Poor"
    
    def _get_rating_description(self, rating: str) -> str:
        """Get description for ESG rating"""
        descriptions = {
            "AAA": "Industry leader in ESG practices",
            "AA": "Strong ESG performance with minimal risks",
            "A": "Above average ESG practices",
            "BBB": "Adequate ESG management",
            "BB": "Some ESG risks identified",
            "B": "Significant ESG risks present",
            "CCC": "Poor ESG performance",
            "C": "Critical ESG issues requiring immediate attention"
        }
        return descriptions.get(rating, "Rating not available")
    
    def _get_date_condition(self, period: str) -> str:
        """Get date condition for SQL queries"""
        if period == "MTD":
            return f"AND posting_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')"
        elif period == "QTD":
            return f"AND posting_date >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL QUARTER(CURDATE())-1 QUARTER), '%Y-%m-01')"
        elif period == "YTD":
            return f"AND posting_date >= DATE_FORMAT(CURDATE(), '%Y-01-01')"
        elif period == "12m":
            return f"AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)"
        else:
            return ""
    
    def get_esg_trends(self, metric: str, period: str = "12m") -> Dict[str, Any]:
        """Get ESG trends for specific metrics"""
        try:
            cache_key = f"esg_trends_{metric}_{period}"
            cached_result = self.cache_manager.get_cached_result(cache_key)
            if cached_result:
                return cached_result
            
            # Generate trend data for the specified metric
            trend_data = self._calculate_metric_trends(metric, period)
            
            self.cache_manager.set_cached_result(cache_key, trend_data, expire_time=3600)
            return trend_data
            
        except Exception as e:
            logger.error(f"Error getting ESG trends: {e}")
            return {"error": str(e)}
    
    def _calculate_metric_trends(self, metric: str, period: str) -> Dict[str, Any]:
        """Calculate trends for specific ESG metrics"""
        try:
            # This would calculate actual trends from historical data
            # For demo purposes, generating sample trend data
            
            months = 12 if period == "12m" else 6
            trend_points = []
            
            for i in range(months):
                month_date = datetime.now() - timedelta(days=30 * i)
                
                # Sample trend calculation (would be real historical data)
                if metric == "carbon_emissions":
                    value = 1000 - (i * 15) + (i % 3 * 10)  # Generally decreasing trend
                elif metric == "renewable_energy":
                    value = 20 + (i * 2.5)  # Generally increasing trend
                elif metric == "employee_satisfaction":
                    value = 4.0 + (i * 0.02)  # Slight improvement
                else:
                    value = 75 + (i % 4 * 2)  # Variable trend
                
                trend_points.append({
                    "date": month_date.strftime("%Y-%m"),
                    "value": round(value, 2)
                })
            
            return {
                "metric": metric,
                "period": period,
                "trend_points": sorted(trend_points, key=lambda x: x["date"]),
                "trend_direction": self._calculate_trend_direction(trend_points),
                "variance": self._calculate_variance(trend_points)
            }
            
        except Exception as e:
            logger.error(f"Error calculating metric trends: {e}")
            return {}
    
    def _calculate_trend_direction(self, trend_points: List[Dict[str, Any]]) -> str:
        """Calculate overall trend direction"""
        if len(trend_points) < 2:
            return "stable"
        
        values = [point["value"] for point in sorted(trend_points, key=lambda x: x["date"])]
        
        if values[-1] > values[0]:
            return "improving"
        elif values[-1] < values[0]:
            return "declining"
        else:
            return "stable"
    
    def _calculate_variance(self, trend_points: List[Dict[str, Any]]) -> float:
        """Calculate variance in trend data"""
        if len(trend_points) < 2:
            return 0
        
        values = [point["value"] for point in trend_points]
        mean_val = sum(values) / len(values)
        variance = sum((x - mean_val) ** 2 for x in values) / len(values)
        
        return round(variance, 2)
    
    def _get_sustainability_targets(self, date_condition: str) -> Dict[str, Any]:
        """Get sustainability targets and progress tracking"""
        try:
            # This would typically come from a sustainability targets tracking system
            # For demo purposes, providing sample targets
            
            current_year = datetime.now().year
            
            return {
                "carbon_neutral_target_year": 2030,
                "renewable_energy_target_pct": 80,
                "waste_reduction_target_pct": 50,
                "water_conservation_target_pct": 40,
                "diversity_target_pct": 40,
                "safety_improvement_target_pct": 25,
                "progress_summary": {
                    "on_track": 4,
                    "behind_schedule": 2,
                    "ahead_of_schedule": 1,
                    "total_targets": 7
                },
                "next_milestone_date": f"{current_year}-12-31",
                "target_review_frequency": "Quarterly"
            }
            
        except Exception as e:
            logger.error(f"Error getting sustainability targets: {e}")
            return {}
    
    def _get_compliance_status(self, date_condition: str) -> Dict[str, Any]:
        """Get compliance tracking status"""
        try:
            return {
                "overall_compliance_rate": 94,
                "environmental_compliance": {
                    "rate": 96,
                    "violations": 1,
                    "certifications": ["ISO 14001", "Energy Star"]
                },
                "social_compliance": {
                    "rate": 92,
                    "violations": 2,
                    "certifications": ["OHSAS 18001", "Fair Trade"]
                },
                "governance_compliance": {
                    "rate": 95,
                    "violations": 1,
                    "certifications": ["SOX", "GDPR"]
                },
                "recent_audits": 3,
                "upcoming_audits": 2,
                "compliance_training_completion": 98
            }
            
        except Exception as e:
            logger.error(f"Error getting compliance status: {e}")
            return {}
    
    def _get_stakeholder_metrics(self, date_condition: str) -> Dict[str, Any]:
        """Get stakeholder engagement metrics"""
        try:
            return {
                "stakeholder_satisfaction_score": 4.1,  # Out of 5
                "investor_engagement_score": 7.8,  # Out of 10
                "customer_engagement_score": 4.3,  # Out of 5
                "community_engagement_score": 3.9,  # Out of 5
                "employee_engagement_score": 4.2,  # Out of 5
                "supplier_engagement_score": 4.0,  # Out of 5
                "stakeholder_feedback_sessions": 12,  # Annual sessions
                "stakeholder_survey_response_rate": 68,  # Percentage
                "materiality_assessment_date": "2025-03-15",
                "stakeholder_communication_channels": 8
            }
            
        except Exception as e:
            logger.error(f"Error getting stakeholder metrics: {e}")
            return {}
    
    def _get_industry_benchmarks(self) -> Dict[str, Any]:
        """Get industry benchmarks for ESG performance"""
        try:
            return {
                "industry": "Manufacturing",  # Would be dynamic based on company
                "peer_comparison": {
                    "esg_score_industry_average": 72,
                    "environmental_score_average": 68,
                    "social_score_average": 74,
                    "governance_score_average": 78
                },
                "top_quartile_benchmarks": {
                    "esg_score": 85,
                    "renewable_energy_pct": 60,
                    "waste_recycling_pct": 80,
                    "employee_satisfaction": 4.5,
                    "diversity_index": 8.0
                },
                "industry_leaders": {
                    "best_environmental": "Company A (Score: 92)",
                    "best_social": "Company B (Score: 89)", 
                    "best_governance": "Company C (Score: 95)"
                },
                "benchmark_sources": ["MSCI ESG", "Sustainalytics", "CDP"],
                "last_updated": "2025-01-15"
            }
            
        except Exception as e:
            logger.error(f"Error getting industry benchmarks: {e}")
            return {}
    
    def _assess_esg_risks(self, date_condition: str) -> Dict[str, Any]:
        """Assess ESG risks and opportunities"""
        try:
            return {
                "environmental_risks": {
                    "climate_risk_exposure": "Medium",
                    "water_scarcity_risk": "Low",
                    "carbon_pricing_risk": "High",
                    "regulatory_risk": "Medium"
                },
                "social_risks": {
                    "talent_attraction_risk": "Medium",
                    "community_relations_risk": "Low", 
                    "supply_chain_labor_risk": "Medium",
                    "health_safety_risk": "Low"
                },
                "governance_risks": {
                    "regulatory_compliance_risk": "Low",
                    "cyber_security_risk": "Medium",
                    "data_privacy_risk": "Medium",
                    "board_effectiveness_risk": "Low"
                },
                "opportunities": {
                    "green_product_innovation": "High",
                    "energy_efficiency_savings": "Medium",
                    "talent_retention": "High",
                    "market_differentiation": "Medium"
                },
                "overall_risk_rating": "Medium",
                "risk_mitigation_actions": 8
            }
            
        except Exception as e:
            logger.error(f"Error assessing ESG risks: {e}")
            return {}
    
    def _track_esg_progress(self, date_condition: str) -> Dict[str, Any]:
        """Track ESG progress against targets"""
        try:
            return {
                "environmental_progress": {
                    "carbon_reduction_progress": 65,  # % toward target
                    "renewable_energy_progress": 55,  # % toward target
                    "waste_reduction_progress": 78,   # % toward target
                    "water_conservation_progress": 42  # % toward target
                },
                "social_progress": {
                    "diversity_progress": 72,  # % toward target
                    "safety_improvement_progress": 88,  # % toward target
                    "employee_satisfaction_progress": 85,  # % toward target
                    "community_investment_progress": 60  # % toward target
                },
                "governance_progress": {
                    "compliance_improvement_progress": 92,  # % toward target
                    "transparency_progress": 75,  # % toward target
                    "risk_management_progress": 83,  # % toward target
                    "stakeholder_engagement_progress": 68  # % toward target
                },
                "overall_progress_score": 72,  # Overall % toward targets
                "on_track_targets": 12,
                "behind_schedule_targets": 4,
                "ahead_of_schedule_targets": 2,
                "next_review_date": "2025-06-30"
            }
            
        except Exception as e:
            logger.error(f"Error tracking ESG progress: {e}")
            return {}
    
    def _assess_reporting_readiness(self, date_condition: str) -> Dict[str, Any]:
        """Assess readiness for ESG reporting and disclosures"""
        try:
            return {
                "data_completeness": {
                    "environmental_data": 88,  # % complete
                    "social_data": 92,  # % complete
                    "governance_data": 85,  # % complete
                    "overall_completeness": 88
                },
                "framework_alignment": {
                    "gri_standards": 78,  # % aligned
                    "sasb_standards": 72,  # % aligned
                    "tcfd_recommendations": 65,  # % aligned
                    "un_global_compact": 82  # % aligned
                },
                "reporting_schedule": {
                    "annual_sustainability_report": "2025-04-30",
                    "quarterly_esg_updates": "2025-03-31", 
                    "cdp_disclosure": "2025-07-31",
                    "investor_esg_briefing": "2025-05-15"
                },
                "assurance_status": {
                    "third_party_verification": True,
                    "data_assurance_level": "Limited",
                    "assurance_provider": "External Auditor",
                    "last_assurance_date": "2024-12-31"
                },
                "stakeholder_readiness": {
                    "board_approval": True, 
                    "management_sign_off": True,
                    "data_validation": 95,  # % validated
                    "disclosure_review": 88  # % reviewed
                }
            }
            
        except Exception as e:
            logger.error(f"Error assessing reporting readiness: {e}")
            return {}
    
    def _calculate_environmental_trends(self, date_condition: str) -> Dict[str, Any]:
        """Calculate environmental performance trends"""
        try:
            # Sample trend data (would be calculated from historical data)
            return {
                "carbon_emissions_trend": "decreasing",
                "renewable_energy_trend": "increasing",
                "waste_generation_trend": "decreasing",
                "water_consumption_trend": "stable",
                "energy_efficiency_trend": "improving"
            }
        except Exception as e:
            logger.error(f"Error calculating environmental trends: {e}")
            return {}
    
    def _calculate_social_trends(self, date_condition: str) -> Dict[str, Any]:
        """Calculate social performance trends"""
        try:
            return {
                "employee_satisfaction_trend": "improving",
                "diversity_index_trend": "improving", 
                "safety_incidents_trend": "decreasing",
                "training_hours_trend": "increasing",
                "community_engagement_trend": "stable"
            }
        except Exception as e:
            logger.error(f"Error calculating social trends: {e}")
            return {}
    
    def _calculate_governance_trends(self, date_condition: str) -> Dict[str, Any]:
        """Calculate governance performance trends"""
        try:
            return {
                "compliance_rate_trend": "improving",
                "audit_findings_trend": "decreasing",
                "board_independence_trend": "stable",
                "transparency_score_trend": "improving",
                "risk_management_trend": "improving"
            }
        except Exception as e:
            logger.error(f"Error calculating governance trends: {e}")
            return {}
    
    def _calculate_improvement_trajectory(self, date_condition: str) -> Dict[str, Any]:
        """Calculate ESG improvement trajectory"""
        try:
            return {
                "trajectory": "positive",
                "improvement_rate": 8.5,  # % annual improvement
                "projected_score_next_year": 78,
                "time_to_target": 24,  # months
                "confidence_level": "high"
            }
        except Exception as e:
            logger.error(f"Error calculating improvement trajectory: {e}")
            return {}
    
    def _get_board_composition(self) -> Dict[str, Any]:
        """Get board composition and governance structure metrics"""
        try:
            # This would typically come from governance data
            # For demo purposes, providing sample board composition
            
            return {
                "board_size": 9,
                "independent_directors": 6,
                "independent_percentage": 67,
                "gender_diversity": {
                    "female_directors": 3,
                    "female_percentage": 33
                },
                "age_diversity": {
                    "average_age": 58,
                    "age_range": "45-72"
                },
                "expertise_diversity": {
                    "financial_expertise": 4,
                    "industry_expertise": 5,
                    "technology_expertise": 2,
                    "esg_expertise": 3
                },
                "tenure_analysis": {
                    "average_tenure": 4.2,
                    "newly_appointed": 2,
                    "long_tenure": 1
                },
                "committee_structure": {
                    "audit_committee": True,
                    "compensation_committee": True,
                    "governance_committee": True,
                    "risk_committee": True,
                    "esg_committee": True
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting board composition: {e}")
            return {}
    
    def _get_ethics_compliance(self, date_condition: str) -> Dict[str, Any]:
        """Get ethics and compliance metrics"""
        try:
            return {
                "code_of_conduct": {
                    "training_completion": 98,  # % completion
                    "acknowledgment_rate": 99,  # % acknowledged
                    "violations_reported": 3,
                    "violations_resolved": 3
                },
                "anti_corruption": {
                    "policy_coverage": 100,  # % employees covered
                    "training_completion": 95,  # % completion
                    "due_diligence_assessments": 12,  # Annual assessments
                    "incidents_reported": 0
                },
                "data_privacy": {
                    "gdpr_compliance": 96,  # % compliance
                    "data_breaches": 1,
                    "breach_response_time": 18,  # Hours to respond
                    "privacy_training_completion": 92
                },
                "whistleblower": {
                    "reports_received": 8,
                    "reports_investigated": 8,
                    "reports_substantiated": 2,
                    "average_resolution_time": 45  # Days
                },
                "regulatory_compliance": {
                    "compliance_rate": 97,  # % compliance
                    "violations": 2,
                    "fines_penalties": 15000,  # Total amount
                    "remediation_actions": 5
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting ethics compliance: {e}")
            return {}
    
    def _get_risk_management_metrics(self, date_condition: str) -> Dict[str, Any]:
        """Get risk management metrics"""
        try:
            return {
                "risk_framework": {
                    "framework_maturity": "Advanced",
                    "risk_appetite_defined": True,
                    "risk_tolerance_set": True,
                    "risk_culture_score": 8.2  # Out of 10
                },
                "risk_identification": {
                    "total_risks_identified": 45,
                    "critical_risks": 8,
                    "high_risks": 12,
                    "medium_risks": 15,
                    "low_risks": 10
                },
                "risk_monitoring": {
                    "kris_tracked": 25,  # Key Risk Indicators
                    "monitoring_frequency": "Monthly",
                    "escalation_procedures": True,
                    "dashboard_availability": True
                },
                "risk_mitigation": {
                    "mitigation_plans": 42,  # Number of plans
                    "implementation_rate": 87,  # % implemented
                    "effectiveness_score": 7.8,  # Out of 10
                    "residual_risk_level": "Medium"
                },
                "crisis_management": {
                    "crisis_plan_updated": "2024-09-30",
                    "simulation_exercises": 2,  # Annual
                    "response_team_trained": True,
                    "communication_plan": True
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting risk management metrics: {e}")
            return {}
    
    def _get_transparency_metrics(self, date_condition: str) -> Dict[str, Any]:
        """Get transparency and disclosure metrics"""
        try:
            return {
                "financial_disclosure": {
                    "annual_report_completeness": 95,  # % complete
                    "quarterly_reporting_timeliness": 100,  # % on time
                    "financial_transparency_score": 8.7,  # Out of 10
                    "auditor_rotation": "Compliant"
                },
                "esg_disclosure": {
                    "sustainability_report_published": True,
                    "esg_data_completeness": 88,  # % complete
                    "third_party_verification": True,
                    "stakeholder_feedback": 4.1  # Out of 5
                },
                "stakeholder_communication": {
                    "investor_meetings": 12,  # Annual
                    "analyst_coverage": 8,  # Number of analysts
                    "shareholder_proposals": 3,
                    "response_rate": 100  # % responded
                },
                "regulatory_filings": {
                    "filing_timeliness": 98,  # % on time
                    "filing_completeness": 99,  # % complete
                    "regulatory_inquiries": 2,
                    "inquiry_response_time": 15  # Average days
                },
                "corporate_website": {
                    "information_completeness": 92,  # % complete
                    "accessibility_compliance": 94,  # % compliant
                    "update_frequency": "Monthly",
                    "multi_language_support": True
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting transparency metrics: {e}")
            return {}
    
    def _get_audit_metrics(self, date_condition: str) -> Dict[str, Any]:
        """Get audit and controls metrics"""
        try:
            return {
                "internal_audit": {
                    "audit_plan_completion": 95,  # % completed
                    "findings_total": 24,
                    "critical_findings": 2,
                    "high_findings": 6,
                    "remediation_rate": 88  # % remediated
                },
                "external_audit": {
                    "clean_opinion": True,
                    "management_letter_points": 4,
                    "material_weaknesses": 0,
                    "deficiencies": 2
                },
                "internal_controls": {
                    "sox_compliance": 97,  # % compliant
                    "control_testing_completion": 100,  # % tested
                    "control_effectiveness": 96,  # % effective
                    "deficiencies_identified": 3
                },
                "audit_committee": {
                    "meetings_held": 6,  # Annual
                    "independence": 100,  # % independent
                    "financial_expertise": True,
                    "performance_evaluation": True
                },
                "compliance_monitoring": {
                    "compliance_tests": 45,  # Annual tests
                    "test_pass_rate": 94,  # % passed
                    "monitoring_frequency": "Quarterly",
                    "reporting_timeliness": 98  # % on time
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting audit metrics: {e}")
            return {}
    
    def _get_stakeholder_rights_metrics(self, date_condition: str) -> Dict[str, Any]:
        """Get stakeholder rights metrics"""
        try:
            return {
                "shareholder_rights": {
                    "voting_rights_protection": True,
                    "minority_rights_protection": True,
                    "shareholder_meeting_attendance": 78,  # % attendance
                    "proxy_voting_participation": 85  # % participation
                },
                "investor_relations": {
                    "investor_satisfaction": 4.2,  # Out of 5
                    "information_accessibility": 92,  # % accessible
                    "response_timeliness": 95,  # % timely
                    "transparency_rating": 8.5  # Out of 10
                },
                "employee_rights": {
                    "collective_bargaining_coverage": 65,  # % covered
                    "grievance_procedures": True,
                    "non_discrimination_policy": True,
                    "workplace_rights_training": 93  # % trained
                },
                "customer_rights": {
                    "privacy_policy_compliance": 96,  # % compliant
                    "complaint_resolution_rate": 98,  # % resolved
                    "customer_satisfaction": 4.3,  # Out of 5
                    "data_protection_compliance": 97  # % compliant
                },
                "community_engagement": {
                    "public_consultation_processes": True,
                    "community_feedback_integration": 78,  # % integrated
                    "local_content_policy": True,
                    "community_investment_transparency": 92  # % transparent
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting stakeholder rights metrics: {e}")
            return {}

    def export_esg_report(self, report_format="json", include_benchmarks=True):
        """Export ESG report in various formats"""
        try:
            # Get current ESG overview
            overview = self.get_esg_overview()
            
            # Include benchmarks if requested
            if include_benchmarks:
                overview["industry_benchmarks"] = self._get_industry_benchmarks()
            
            # Add report metadata
            report_data = {
                "report_info": {
                    "generated_at": frappe.utils.now(),
                    "period": f"{self.start_date} to {self.end_date}",
                    "company": self.company,
                    "format": report_format
                },
                "esg_data": overview
            }
            
            if report_format == "json":
                return report_data
            elif report_format == "html":
                return self._format_html_report(report_data)
            else:
                return report_data
                
        except Exception as e:
            logger.error(f"Error exporting ESG report: {e}")
            return None

    def _format_html_report(self, data):
        """Format ESG data as HTML report"""
        html = f"""
        <html>
        <head><title>ESG Report - {data['report_info']['company']}</title></head>
        <body>
            <h1>ESG Intelligence Report</h1>
            <p><strong>Period:</strong> {data['report_info']['period']}</p>
            <p><strong>Generated:</strong> {data['report_info']['generated_at']}</p>
            
            <h2>ESG Score: {data['esg_data'].get('overall_score', 0)}/100</h2>
            <h3>Environmental Score: {data['esg_data'].get('environmental_score', 0)}/100</h3>
            <h3>Social Score: {data['esg_data'].get('social_score', 0)}/100</h3>
            <h3>Governance Score: {data['esg_data'].get('governance_score', 0)}/100</h3>
        </body>
        </html>
        """
        return html