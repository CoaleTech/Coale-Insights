from __future__ import annotations
import frappe
from frappe import _
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Dict, Any, List, Optional, Set
from collections import defaultdict
from insights.ml.base import BaseMLModel

if TYPE_CHECKING:
    import pandas as pd
    import numpy as np


class ProductRecommendations(BaseMLModel):
    """
    Product Recommendation Engine
    
    Methods:
    1. Association Rules (Market Basket Analysis)
       - Frequently bought together
       - Apriori algorithm
       
    2. Collaborative Filtering
       - Item-based similarity
       - Customer-based similarity
       
    3. Content-Based
       - Similar items by category
       - Similar items by attributes
    """
    
    def __init__(self):
        super().__init__()
        self.model_name = "ProductRecommendations"
        self.item_similarity_matrix = None
        self.association_rules = []
        
    def _get_transaction_data(self) -> pd.DataFrame:
        """Get transaction data for association rules"""
        query = """
            SELECT 
                si.name as transaction_id,
                si.customer,
                sii.item_code,
                sii.qty,
                sii.amount,
                si.posting_date
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON sii.parent = si.name
            WHERE si.docstatus = 1
            ORDER BY si.name, sii.item_code
        """
        return self.get_training_data(query)
    
    def _get_item_info(self) -> pd.DataFrame:
        """Get item metadata"""
        query = """
            SELECT 
                name as item_code,
                item_name,
                item_group,
                brand,
                description
            FROM `tabItem`
            WHERE disabled = 0
        """
        return self.get_training_data(query)
    
    def _get_customer_purchases(self) -> pd.DataFrame:
        """Get customer purchase history for collaborative filtering"""
        query = """
            SELECT 
                si.customer,
                sii.item_code,
                SUM(sii.qty) as total_qty,
                COUNT(DISTINCT si.name) as purchase_count
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON sii.parent = si.name
            WHERE si.docstatus = 1
            GROUP BY si.customer, sii.item_code
        """
        return self.get_training_data(query)
    
    def _build_transaction_sets(self, df: pd.DataFrame) -> List[Set[str]]:
        """Build transaction sets for association rules"""
        transactions = []
        for txn_id, group in df.groupby('transaction_id'):
            items = set(group['item_code'].tolist())
            if len(items) >= 2:  # Only include transactions with 2+ items
                transactions.append(items)
        return transactions
    
    def _calculate_support(self, itemset: Set[str], transactions: List[Set[str]]) -> float:
        """Calculate support for an itemset"""
        count = sum(1 for txn in transactions if itemset.issubset(txn))
        return count / len(transactions) if transactions else 0
    
    def _find_frequent_itemsets(
        self, 
        transactions: List[Set[str]], 
        min_support: float = 0.01
    ) -> Dict[frozenset, float]:
        """Find frequent itemsets using Apriori algorithm"""
        # Get all unique items
        all_items = set()
        for txn in transactions:
            all_items.update(txn)
        
        # Find frequent 1-itemsets
        frequent = {}
        for item in all_items:
            itemset = frozenset([item])
            support = self._calculate_support({item}, transactions)
            if support >= min_support:
                frequent[itemset] = support
        
        # Find frequent k-itemsets
        k = 2
        current_frequent = list(frequent.keys())
        
        while current_frequent and k <= 3:  # Limit to 3-itemsets for performance
            # Generate candidates
            candidates = []
            for i, itemset1 in enumerate(current_frequent):
                for itemset2 in current_frequent[i+1:]:
                    union = itemset1 | itemset2
                    if len(union) == k:
                        candidates.append(union)
            
            # Filter by support
            current_frequent = []
            for candidate in set(map(frozenset, candidates)):
                support = self._calculate_support(set(candidate), transactions)
                if support >= min_support:
                    frequent[candidate] = support
                    current_frequent.append(candidate)
            
            k += 1
        
        return frequent
    
    def _generate_association_rules(
        self, 
        frequent_itemsets: Dict[frozenset, float],
        transactions: List[Set[str]],
        min_confidence: float = 0.3
    ) -> List[Dict[str, Any]]:
        """Generate association rules from frequent itemsets"""
        rules = []
        
        for itemset, support in frequent_itemsets.items():
            if len(itemset) < 2:
                continue
            
            items = list(itemset)
            
            # Generate rules for each possible antecedent
            for i, item in enumerate(items):
                antecedent = frozenset([item])
                consequent = frozenset(items[:i] + items[i+1:])
                
                # Calculate confidence
                antecedent_support = frequent_itemsets.get(antecedent, 0)
                if antecedent_support > 0:
                    confidence = support / antecedent_support
                    
                    if confidence >= min_confidence:
                        # Calculate lift
                        consequent_support = self._calculate_support(
                            set(consequent), transactions
                        )
                        lift = confidence / consequent_support if consequent_support > 0 else 0
                        
                        rules.append({
                            "antecedent": list(antecedent),
                            "consequent": list(consequent),
                            "support": round(support, 4),
                            "confidence": round(confidence, 4),
                            "lift": round(lift, 2)
                        })
        
        # Sort by lift
        rules.sort(key=lambda x: x['lift'], reverse=True)
        return rules
    
    def _build_item_similarity_matrix(self, df: pd.DataFrame) -> pd.DataFrame:
        """Build item-item similarity matrix using cosine similarity"""
        import pandas as pd

        # Create customer-item matrix
        customer_item = df.pivot_table(
            index='customer',
            columns='item_code',
            values='total_qty',
            fill_value=0
        )
        
        # Calculate item-item similarity (cosine)
        from sklearn.metrics.pairwise import cosine_similarity
        
        item_matrix = customer_item.T.values
        similarity = cosine_similarity(item_matrix)
        
        similarity_df = pd.DataFrame(
            similarity,
            index=customer_item.columns,
            columns=customer_item.columns
        )
        
        return similarity_df
    
    def train(self, min_support: float = 0.01, min_confidence: float = 0.3) -> Dict[str, Any]:
        """Train recommendation models"""
        import numpy as np

        # Get data
        txn_df = self._get_transaction_data()
        
        if txn_df.empty:
            return {
                "status": "error",
                "message": _("No transaction data found")
            }
        
        # Build transaction sets
        transactions = self._build_transaction_sets(txn_df)
        
        if len(transactions) < 10:
            return {
                "status": "error",
                "message": _("Insufficient transactions for analysis (need at least 10)")
            }
        
        # Find frequent itemsets
        frequent_itemsets = self._find_frequent_itemsets(transactions, min_support)
        
        # Generate association rules
        self.association_rules = self._generate_association_rules(
            frequent_itemsets, transactions, min_confidence
        )
        
        # Build collaborative filtering model
        cust_purchases = self._get_customer_purchases()
        
        cf_results = {}
        if not cust_purchases.empty and len(cust_purchases['item_code'].unique()) > 5:
            try:
                self.item_similarity_matrix = self._build_item_similarity_matrix(cust_purchases)
                cf_results = {
                    "items_in_matrix": len(self.item_similarity_matrix),
                    "status": "trained"
                }
            except Exception as e:
                cf_results = {"status": "failed", "error": str(e)}
        
        # Get item info for enrichment
        item_info = self._get_item_info()
        item_dict = dict(zip(item_info['item_code'], item_info['item_name']))
        
        # Enrich rules with item names
        for rule in self.association_rules:
            rule['antecedent_names'] = [item_dict.get(i, i) for i in rule['antecedent']]
            rule['consequent_names'] = [item_dict.get(i, i) for i in rule['consequent']]
        
        # Build frequently bought together pairs
        fbt_pairs = self._get_frequently_bought_together(txn_df, item_dict)
        
        results = {
            "status": "success",
            "training_date": datetime.now().isoformat(),
            "transaction_summary": {
                "total_transactions": len(transactions),
                "total_items": len(set().union(*transactions)) if transactions else 0,
                "avg_basket_size": round(np.mean([len(t) for t in transactions]), 2)
            },
            "association_rules": {
                "total_rules": len(self.association_rules),
                "top_rules": self.association_rules[:20]
            },
            "collaborative_filtering": cf_results,
            "frequently_bought_together": fbt_pairs[:30]
        }
        
        # Cache results
        self.cache_results("product_recommendations", results, expires_in_hours=24)
        
        # Log training
        self.log_training({
            "transactions": len(transactions),
            "rules_generated": len(self.association_rules)
        })
        
        return results
    
    def predict(self, data: Any) -> Dict[str, Any]:
        """
        Get product recommendations for a customer or item
        
        Args:
            data: Dict with 'customer_id' or 'item_code' key
            
        Returns:
            Dict with recommendations
        """
        if isinstance(data, dict):
            customer_id = data.get('customer_id')
            item_code = data.get('item_code')
            top_n = data.get('top_n', 5)
        else:
            return {"status": "error", "message": _("Invalid input - expected dict with customer_id or item_code")}
        
        # Load cached rules if not in memory
        if not self.association_rules:
            cached = self.get_cached_results("product_recommendations")
            if cached and cached.get('status') == 'success':
                rules_data = cached.get('association_rules', {})
                self.association_rules = rules_data.get('top_rules', []) if isinstance(rules_data, dict) else rules_data
        
        if customer_id:
            return self._get_customer_recommendations(customer_id, top_n)
        elif item_code:
            return self.get_recommendations_for_item(item_code, top_n)
        else:
            return {"status": "error", "message": _("Provide customer_id or item_code")}
    
    def _get_customer_recommendations(self, customer_id: str, top_n: int = 5) -> Dict[str, Any]:
        """Get recommendations for a customer based on their purchase history"""
        # Get items this customer has purchased
        purchased = frappe.db.sql("""
            SELECT DISTINCT sii.item_code
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON sii.parent = si.name
            WHERE si.customer = %(customer_id)s AND si.docstatus = 1
        """, {"customer_id": customer_id}, as_dict=True)
        
        purchased_set = {item['item_code'] for item in purchased}
        
        if not purchased_set:
            return {"status": "success", "recommendations": [], "message": _("No purchase history found")}
        
        recommendations = []
        seen = set()
        
        for rule in self.association_rules:
            antecedent = set(rule.get('antecedent', []))
            consequent = rule.get('consequent', [])
            
            if antecedent.issubset(purchased_set):
                for item_code in consequent:
                    if item_code not in purchased_set and item_code not in seen:
                        seen.add(item_code)
                        item_info = frappe.db.get_value("Item", item_code, ["item_name", "item_group"], as_dict=True)
                        if item_info:
                            recommendations.append({
                                "item_code": item_code,
                                "item_name": item_info.get('item_name', item_code),
                                "item_group": item_info.get('item_group', ''),
                                "confidence": rule.get('confidence', 0),
                                "lift": rule.get('lift', 0),
                                "reason": "Frequently bought together"
                            })
        
        recommendations.sort(key=lambda x: x['confidence'], reverse=True)
        return {"status": "success", "recommendations": recommendations[:top_n]}

    def _get_frequently_bought_together(
        self, 
        txn_df: pd.DataFrame, 
        item_dict: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """Get frequently bought together pairs"""
        pair_counts = defaultdict(int)
        item_counts = defaultdict(int)
        
        for txn_id, group in txn_df.groupby('transaction_id'):
            items = group['item_code'].tolist()
            
            for item in items:
                item_counts[item] += 1
            
            for i, item1 in enumerate(items):
                for item2 in items[i+1:]:
                    pair = tuple(sorted([item1, item2]))
                    pair_counts[pair] += 1
        
        # Calculate metrics
        total_txns = txn_df['transaction_id'].nunique()
        pairs = []
        
        for pair, count in pair_counts.items():
            if count >= 3:  # Minimum 3 co-occurrences
                item1, item2 = pair
                support = count / total_txns
                
                # Expected co-occurrence
                expected = (item_counts[item1] / total_txns) * (item_counts[item2] / total_txns)
                lift = support / expected if expected > 0 else 0
                
                pairs.append({
                    "item1": item1,
                    "item1_name": item_dict.get(item1, item1),
                    "item2": item2,
                    "item2_name": item_dict.get(item2, item2),
                    "co_occurrence_count": count,
                    "support": round(support, 4),
                    "lift": round(lift, 2)
                })
        
        # Sort by lift
        pairs.sort(key=lambda x: x['lift'], reverse=True)
        return pairs
    
    def get_recommendations_for_item(self, item_code: str, top_n: int = 5) -> Dict[str, Any]:
        """Get recommendations for a specific item"""
        recommendations = []
        
        # Method 1: From association rules
        for rule in self.association_rules:
            if item_code in rule['antecedent']:
                for conseq in rule['consequent']:
                    recommendations.append({
                        "item_code": conseq,
                        "item_name": rule['consequent_names'][rule['consequent'].index(conseq)],
                        "confidence": rule['confidence'],
                        "lift": rule['lift'],
                        "method": "association_rules"
                    })
        
        # Method 2: From item similarity
        if self.item_similarity_matrix is not None and item_code in self.item_similarity_matrix.columns:
            similar_items = self.item_similarity_matrix[item_code].nlargest(top_n + 1)[1:]  # Exclude self
            
            item_info = self._get_item_info()
            item_dict = dict(zip(item_info['item_code'], item_info['item_name']))
            
            for sim_item, score in similar_items.items():
                if score > 0.1:  # Minimum similarity threshold
                    recommendations.append({
                        "item_code": sim_item,
                        "item_name": item_dict.get(sim_item, sim_item),
                        "similarity": round(score, 3),
                        "method": "collaborative_filtering"
                    })
        
        # Deduplicate and sort
        seen = set()
        unique_recs = []
        for rec in recommendations:
            if rec['item_code'] not in seen and rec['item_code'] != item_code:
                seen.add(rec['item_code'])
                unique_recs.append(rec)
        
        # Sort by confidence/similarity
        unique_recs.sort(
            key=lambda x: x.get('confidence', 0) + x.get('similarity', 0),
            reverse=True
        )
        
        return {
            "status": "success",
            "item_code": item_code,
            "recommendations": unique_recs[:top_n]
        }
    
    def get_recommendations_for_customer(self, customer: str, top_n: int = 10) -> Dict[str, Any]:
        """Get personalized recommendations for a customer"""
        # Get customer's purchase history
        query = f"""
            SELECT DISTINCT sii.item_code
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON sii.parent = si.name
            WHERE si.docstatus = 1 AND si.customer = '{frappe.db.escape(customer)}'
        """
        purchased_df = self.get_training_data(query)
        
        if purchased_df.empty:
            return {
                "status": "success",
                "message": _("No purchase history for customer"),
                "recommendations": []
            }
        
        purchased_items = set(purchased_df['item_code'].tolist())
        
        # Get recommendations for each purchased item
        all_recommendations = []
        for item in list(purchased_items)[:10]:  # Limit to avoid too many lookups
            recs = self.get_recommendations_for_item(item, top_n=5)
            for rec in recs.get('recommendations', []):
                if rec['item_code'] not in purchased_items:
                    rec['based_on'] = item
                    all_recommendations.append(rec)
        
        # Aggregate recommendations
        item_scores = defaultdict(lambda: {"score": 0, "count": 0, "based_on": []})
        
        for rec in all_recommendations:
            item = rec['item_code']
            score = rec.get('confidence', 0) + rec.get('similarity', 0)
            item_scores[item]['score'] += score
            item_scores[item]['count'] += 1
            item_scores[item]['based_on'].append(rec['based_on'])
            item_scores[item]['item_name'] = rec['item_name']
        
        # Create final recommendations
        final_recs = []
        for item_code, data in item_scores.items():
            final_recs.append({
                "item_code": item_code,
                "item_name": data['item_name'],
                "relevance_score": round(data['score'] / data['count'], 3),
                "recommendation_count": data['count'],
                "based_on_items": list(set(data['based_on']))[:3]
            })
        
        final_recs.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        return {
            "status": "success",
            "customer": customer,
            "purchased_items_count": len(purchased_items),
            "recommendations": final_recs[:top_n]
        }
    
    def get_cart_recommendations(self, cart_items: List[str], top_n: int = 5) -> Dict[str, Any]:
        """Get recommendations based on current cart items"""
        recommendations = []
        
        for item in cart_items:
            recs = self.get_recommendations_for_item(item, top_n=3)
            for rec in recs.get('recommendations', []):
                if rec['item_code'] not in cart_items:
                    rec['because_of'] = item
                    recommendations.append(rec)
        
        # Deduplicate and score
        item_scores = defaultdict(lambda: {"score": 0, "sources": []})
        
        for rec in recommendations:
            item = rec['item_code']
            score = rec.get('confidence', 0) + rec.get('lift', 0) / 10
            item_scores[item]['score'] += score
            item_scores[item]['sources'].append(rec['because_of'])
            item_scores[item]['item_name'] = rec['item_name']
        
        final_recs = []
        for item_code, data in item_scores.items():
            final_recs.append({
                "item_code": item_code,
                "item_name": data['item_name'],
                "relevance_score": round(data['score'], 3),
                "recommended_because": list(set(data['sources']))
            })
        
        final_recs.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        return {
            "status": "success",
            "cart_items": cart_items,
            "recommendations": final_recs[:top_n]
        }


# API Functions
def run_recommendation_training(min_support: float = 0.01, min_confidence: float = 0.3) -> Dict[str, Any]:
    """Train recommendation models"""
    model = ProductRecommendations()
    return model.train(float(min_support), float(min_confidence))


def get_item_recommendations(item_code: str, top_n: int = 5) -> Dict[str, Any]:
    """Get recommendations for an item"""
    model = ProductRecommendations()
    
    # Load cached model
    cached = model.get_cached_results("product_recommendations")
    if cached and cached.get('association_rules'):
        model.association_rules = cached['association_rules'].get('top_rules', [])
    else:
        model.train()
    
    return model.get_recommendations_for_item(item_code, int(top_n))


def get_customer_recommendations(customer: str, top_n: int = 10) -> Dict[str, Any]:
    """Get recommendations for a customer"""
    model = ProductRecommendations()
    
    # Load cached model
    cached = model.get_cached_results("product_recommendations")
    if cached and cached.get('association_rules'):
        model.association_rules = cached['association_rules'].get('top_rules', [])
    else:
        model.train()
    
    return model.get_recommendations_for_customer(customer, int(top_n))


def get_cart_recommendations(cart_items: str, top_n: int = 5) -> Dict[str, Any]:
    """Get recommendations for cart items"""
    import json
    
    model = ProductRecommendations()
    
    # Parse cart items
    if isinstance(cart_items, str):
        cart_items = json.loads(cart_items)
    
    # Load cached model
    cached = model.get_cached_results("product_recommendations")
    if cached and cached.get('association_rules'):
        model.association_rules = cached['association_rules'].get('top_rules', [])
    else:
        model.train()
    
    return model.get_cart_recommendations(cart_items, int(top_n))


def get_frequently_bought_together() -> Dict[str, Any]:
    """Get frequently bought together pairs"""
    model = ProductRecommendations()
    cached = model.get_cached_results("product_recommendations")
    
    if cached and cached.get('frequently_bought_together'):
        return {
            "status": "success",
            "pairs": cached['frequently_bought_together']
        }
    
    result = model.train()
    return {
        "status": "success",
        "pairs": result.get('frequently_bought_together', [])
    }
