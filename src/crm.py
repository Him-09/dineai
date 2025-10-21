"""
Simplified CRM module for storing customer information to recognize repeat customers
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from db import supabase

logger = logging.getLogger("restaurant-crm")

class CRMManager:
    """Simple CRM for customer recognition using phone as primary key"""
    
    def __init__(self):
        self.table_name = "crm_contacts"
    
    async def store_customer_info(
        self, 
        phone: str,
        name: Optional[str] = None,
        interaction_summary: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Store or update customer information using phone as primary key
        
        Args:
            phone: Customer's phone number (primary key)
            name: Customer's name if provided
            interaction_summary: Summary of the interaction
            
        Returns:
            Dictionary with operation result
        """
        try:
            if not phone:
                return {"success": False, "error": "Phone number is required"}
            
            # Check if customer already exists
            existing_contact = self.get_customer_by_phone(phone)
            
            if existing_contact:
                # Update existing customer
                return await self.update_customer(
                    phone=phone,
                    name=name,
                    interaction_summary=interaction_summary
                )
            else:
                # Create new customer
                return await self.create_customer(
                    phone=phone,
                    name=name,
                    interaction_summary=interaction_summary
                )
                
        except Exception as e:
            logger.error(f"Error storing customer info: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def create_customer(
        self,
        phone: str,
        name: Optional[str] = None,
        interaction_summary: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new customer record"""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            formatted_interaction = f"[{timestamp}] {interaction_summary or 'Initial contact'}"
            
            customer_data = {
                "phone": phone,
                "name": name,
                "last_interaction": formatted_interaction,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            
            # Remove None values
            customer_data = {k: v for k, v in customer_data.items() if v is not None}
            
            result = supabase.table(self.table_name).insert(customer_data).execute()
            
            if result.data:
                logger.info(f"Created new customer for phone: {phone}")
                return {"success": True, "data": result.data[0], "action": "created"}
            else:
                return {"success": False, "error": "No data returned from insert"}
                
        except Exception as e:
            logger.error(f"Error creating customer: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def update_customer(
        self,
        phone: str,
        name: Optional[str] = None,
        interaction_summary: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update an existing customer record"""
        try:
            update_data = {"updated_at": datetime.now().isoformat()}
            
            if name is not None:
                update_data["name"] = name
                
            if interaction_summary is not None:
                # Get existing customer to append to current last_interaction
                existing_customer = self.get_customer_by_phone(phone)
                if existing_customer and existing_customer.get("last_interaction"):
                    # Append new summary to existing interactions with timestamp
                    current_interactions = existing_customer["last_interaction"]
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
                    new_interaction = f"{current_interactions}\n[{timestamp}] {interaction_summary}"
                    update_data["last_interaction"] = new_interaction
                else:
                    # First interaction or no existing summary
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
                    update_data["last_interaction"] = f"[{timestamp}] {interaction_summary}"
            
            result = supabase.table(self.table_name).update(update_data).eq("phone", phone).execute()
            
            if result.data:
                logger.info(f"Updated customer: {phone}")
                return {"success": True, "data": result.data[0], "action": "updated"}
            else:
                return {"success": False, "error": "No data returned from update"}
                
        except Exception as e:
            logger.error(f"Error updating customer: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def get_customer_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        """Retrieve customer by phone number"""
        try:
            result = supabase.table(self.table_name).select("*").eq("phone", phone).execute()
            
            if result.data:
                return result.data[0]
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving customer by phone {phone}: {str(e)}")
            return None
    
    def get_recent_customers(self, limit: int = 10) -> list:
        """Get recent customers"""
        try:
            result = supabase.table(self.table_name).select("*").order("created_at", desc=True).limit(limit).execute()
            return result.data or []
            
        except Exception as e:
            logger.error(f"Error retrieving recent customers: {str(e)}")
            return []

    async def add_interaction_note(self, phone: str, note: str) -> Dict[str, Any]:
        """Add a note to an existing customer's last_interaction field"""
        try:
            customer = self.get_customer_by_phone(phone)
            if not customer:
                # Auto-create customer if doesn't exist
                logger.info(f"Auto-creating customer for phone {phone} to attach note")
                create_result = await self.create_customer(
                    phone=phone,
                    interaction_summary="Auto-created to store interaction note"
                )
                if not create_result.get("success"):
                    return {"success": False, "error": "Failed to auto-create customer for note"}
                customer = self.get_customer_by_phone(phone)
                if not customer:
                    return {"success": False, "error": "Customer could not be retrieved after auto-create"}
            
            current_interaction = customer.get("last_interaction", "")
            updated_interaction = f"{current_interaction}\n{datetime.now().strftime('%Y-%m-%d %H:%M')}: {note}"
            
            return await self.update_customer(
                phone=phone,
                interaction_summary=updated_interaction
            )
            
        except Exception as e:
            logger.error(f"Error adding interaction note: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def search_customers(self, query: str) -> list:
        """Search customers by name or phone"""
        try:
            # Search by name
            name_results = supabase.table(self.table_name).select("*").ilike("name", f"%{query}%").execute()
            
            # Search by phone
            phone_results = supabase.table(self.table_name).select("*").ilike("phone", f"%{query}%").execute()
            
            # Combine and deduplicate results
            all_results = (name_results.data or []) + (phone_results.data or [])
            unique_results = {customer["phone"]: customer for customer in all_results}.values()
            
            return list(unique_results)
            
        except Exception as e:
            logger.error(f"Error searching customers: {str(e)}")
            return []

# Global CRM manager instance
crm_manager = CRMManager()

# Convenience functions for easy import
async def store_customer_info(phone: str, name: str | None = None, interaction_summary: str | None = None):
    """Convenience function to store customer information"""
    return await crm_manager.store_customer_info(phone, name, interaction_summary)

async def add_interaction_note(phone: str, note: str):
    """Convenience function to add interaction note"""
    return await crm_manager.add_interaction_note(phone, note)

def get_customer_by_phone(phone: str):
    """Convenience function to get customer by phone"""
    return crm_manager.get_customer_by_phone(phone)

def get_recent_customers(limit: int = 10):
    """Convenience function to get recent customers"""
    return crm_manager.get_recent_customers(limit)