#!/usr/bin/env python3
"""
Database models for offline team utilities
"""

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class User(db.Model):
    """User model - minimal model for relationships (actual user management is in auth blueprint)"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), nullable=False)
    # Note: Other fields like password_hash, is_admin, etc. exist in the database
    # but are managed by the auth blueprint, not SQLAlchemy


class Brand(db.Model):
    """Brand model"""
    __tablename__ = 'brands'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    code = db.Column(db.String(255), nullable=True, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    categories = db.relationship('Category', back_populates='brand', cascade='all, delete-orphan')
    items = db.relationship('Item', back_populates='brand', cascade='all, delete-orphan')
    customers = db.relationship('ChannelCustomer', back_populates='brand')
    sellthrough_data = db.relationship('SellthroughData', back_populates='brand')
    netsuite_data = db.relationship('NetsuiteData', back_populates='brand')
    
    def __repr__(self):
        return f'<Brand {self.name}>'


class Category(db.Model):
    """Category model - categories of products within a brand"""
    __tablename__ = 'categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    brand = db.relationship('Brand', back_populates='categories')
    items = db.relationship('Item', back_populates='category', cascade='all, delete-orphan')
    
    # Unique constraint on name per brand
    __table_args__ = (db.UniqueConstraint('name', 'brand_id', name='uq_category_brand'),)
    
    def __repr__(self):
        return f'<Category {self.name} (Brand: {self.brand_id})>'


class Channel(db.Model):
    """Channel model - channels like Walmart where products are sold"""
    __tablename__ = 'channels'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    netsuite_include = db.Column(db.Boolean, default=True, nullable=False)  # Include in Netsuite dashboard
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    customers = db.relationship('ChannelCustomer', back_populates='channel', cascade='all, delete-orphan')
    sellthrough_data = db.relationship('SellthroughData', back_populates='channel')
    netsuite_data = db.relationship('NetsuiteData', back_populates='channel')
    channel_items = db.relationship('ChannelItem', back_populates='channel', cascade='all, delete-orphan')
    netsuite_codes = db.relationship('NetsuiteCode', back_populates='channel', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Channel {self.name}>'


class ChannelCustomerType(db.Model):
    """Channel Customer Type model"""
    __tablename__ = 'channel_customer_types'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    color = db.Column(db.String(7), nullable=True)  # Hex color code (e.g., #F59E0B)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    customers = db.relationship('ChannelCustomer', back_populates='customer_type', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<ChannelCustomerType {self.name}>'


class ChannelCustomer(db.Model):
    """ChannelCustomer model - customers within a channel"""
    __tablename__ = 'channel_customers'
    
    id = db.Column(db.Integer, primary_key=True)
    channel_id = db.Column(db.Integer, db.ForeignKey('channels.id'), nullable=False)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=True)
    customer_type_id = db.Column(db.Integer, db.ForeignKey('channel_customer_types.id'), nullable=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    channel = db.relationship('Channel', back_populates='customers')
    brand = db.relationship('Brand', back_populates='customers')
    customer_type = db.relationship('ChannelCustomerType', back_populates='customers')
    sellthrough_data = db.relationship('SellthroughData', back_populates='customer')
    netsuite_data = db.relationship('NetsuiteData', back_populates='customer')
    netsuite_codes = db.relationship('NetsuiteCode', back_populates='customer')
    
    # Unique constraint on name per channel
    __table_args__ = (db.UniqueConstraint('name', 'channel_id', name='uq_customer_channel'),)
    
    def __repr__(self):
        return f'<ChannelCustomer {self.name} (Channel: {self.channel_id})>'


class Asin(db.Model):
    """ASIN model - Amazon Standard Identification Number"""
    __tablename__ = 'asins'
    
    id = db.Column(db.Integer, primary_key=True)
    asin = db.Column(db.String(255), nullable=False, unique=True)
    img_url = db.Column(db.String(512), nullable=True)
    title = db.Column(db.String(512), nullable=True)
    scraped_at = db.Column(db.Date, nullable=True)
    scraped_json = db.Column(db.Text, nullable=True)  # JSON string of scraped data from Pangolin
    scraped_json_rapid = db.Column(db.Text, nullable=True)  # JSON string of scraped data from RapidAPI
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    items = db.relationship('Item', back_populates='asin_obj')
    
    def __repr__(self):
        return f'<Asin {self.asin}>'


class Item(db.Model):
    """Item model - specific products sold through channels"""
    __tablename__ = 'items'
    
    id = db.Column(db.Integer, primary_key=True)
    essor_code = db.Column(db.String(255), nullable=True, unique=True)
    essor_name = db.Column(db.String(255), nullable=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    asin_id = db.Column(db.Integer, db.ForeignKey('asins.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    brand = db.relationship('Brand', back_populates='items')
    category = db.relationship('Category', back_populates='items')
    asin_obj = db.relationship('Asin', back_populates='items')
    sellthrough_data = db.relationship('SellthroughData', back_populates='item')
    netsuite_data = db.relationship('NetsuiteData', back_populates='item')
    channel_items = db.relationship('ChannelItem', back_populates='item', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Item {self.essor_code} - {self.essor_name}>'


class ChannelItem(db.Model):
    """ChannelItem model - links items to channels with channel-specific codes and names"""
    __tablename__ = 'channel_items'
    
    id = db.Column(db.Integer, primary_key=True)
    channel_id = db.Column(db.Integer, db.ForeignKey('channels.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('items.id'), nullable=False)
    channel_code = db.Column(db.String(255), nullable=False)
    channel_name = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    channel = db.relationship('Channel', back_populates='channel_items')
    item = db.relationship('Item', back_populates='channel_items')
    
    # Unique constraint on channel_id and item_id
    __table_args__ = (db.UniqueConstraint('channel_id', 'item_id', name='uq_channel_item'),)
    
    def __repr__(self):
        return f'<ChannelItem {self.channel_code} - {self.channel_name}>'


class SellthroughData(db.Model):
    """Sellthrough data model"""
    __tablename__ = 'sellthrough_data'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('items.id'), nullable=False)
    channel_id = db.Column(db.Integer, db.ForeignKey('channels.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('channel_customers.id'), nullable=True)
    revenues = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    units = db.Column(db.Integer, nullable=False, default=0)
    stores = db.Column(db.Integer, nullable=False, default=0)
    oos = db.Column(db.Numeric(5, 2), nullable=True)  # Out of stock percentage (stored as 100, so 50% = 50)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    brand = db.relationship('Brand', back_populates='sellthrough_data')
    item = db.relationship('Item', back_populates='sellthrough_data')
    channel = db.relationship('Channel', back_populates='sellthrough_data')
    customer = db.relationship('ChannelCustomer', back_populates='sellthrough_data')
    
    # Index for faster queries
    __table_args__ = (
        db.Index('idx_sellthrough_date', 'date'),
        db.Index('idx_sellthrough_brand_date', 'brand_id', 'date'),
        db.Index('idx_sellthrough_item_date', 'item_id', 'date'),
        db.UniqueConstraint('date', 'channel_id', 'item_id', 'customer_id', name='uq_sellthrough_unique'),
    )
    
    def __repr__(self):
        return f'<SellthroughData {self.date} - Item: {self.item_id}>'


class NetsuiteData(db.Model):
    """Netsuite revenue data model"""
    __tablename__ = 'netsuite_data'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('items.id'), nullable=False)
    channel_id = db.Column(db.Integer, db.ForeignKey('channels.id'), nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('channel_customers.id'), nullable=True)
    internal_id = db.Column(db.String(255), nullable=True)  # Netsuite INTERNAL_ID
    revenues = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    units = db.Column(db.Integer, nullable=False, default=0)
    retailer_code = db.Column(db.String(10), nullable=True)  # First 5 chars of retailer name
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    brand = db.relationship('Brand', back_populates='netsuite_data')
    item = db.relationship('Item', back_populates='netsuite_data')
    channel = db.relationship('Channel', back_populates='netsuite_data')
    customer = db.relationship('ChannelCustomer', back_populates='netsuite_data')
    
    # Index for faster queries
    __table_args__ = (
        db.Index('idx_netsuite_date', 'date'),
        db.Index('idx_netsuite_brand_date', 'brand_id', 'date'),
        db.Index('idx_netsuite_item_date', 'item_id', 'date'),
        db.UniqueConstraint('date', 'channel_id', 'item_id', 'customer_id', name='uq_netsuite_unique'),
    )
    
    def __repr__(self):
        return f'<NetsuiteData {self.date} - Item: {self.item_id}>'


class NetsuiteCode(db.Model):
    """NetsuiteCode model - maps netsuite codes to channels and customers"""
    __tablename__ = 'netsuite_codes'
    
    id = db.Column(db.Integer, primary_key=True)
    netsuite_code = db.Column(db.String(10), nullable=False)
    netsuite_name = db.Column(db.String(255), nullable=True)
    channel_id = db.Column(db.Integer, db.ForeignKey('channels.id'), nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('channel_customers.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    channel = db.relationship('Channel', back_populates='netsuite_codes')
    customer = db.relationship('ChannelCustomer', back_populates='netsuite_codes')
    
    # Unique constraint on netsuite_code (one code can only map to one channel)
    __table_args__ = (
        db.UniqueConstraint('netsuite_code', name='uq_netsuite_code'),
        db.Index('idx_netsuite_code', 'netsuite_code'),
    )
    
    def __repr__(self):
        return f'<NetsuiteCode {self.netsuite_code} -> Channel: {self.channel_id}>'


class ImportError(db.Model):
    """ImportError model - stores import errors for debugging"""
    __tablename__ = 'import_errors'
    
    id = db.Column(db.Integer, primary_key=True)
    import_channel = db.Column(db.String(50), nullable=False)  # 'snowflake', 'csv', etc.
    import_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    error_data = db.Column(db.Text, nullable=False)  # JSON string of the problematic row
    error_message = db.Column(db.Text, nullable=True)  # Error message
    row_number = db.Column(db.Integer, nullable=True)  # Row number if available
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Index for faster queries
    __table_args__ = (
        db.Index('idx_import_error_channel_date', 'import_channel', 'import_date'),
    )
    
    def __repr__(self):
        return f'<ImportError {self.import_channel} - {self.import_date}>'


class SpinsChannel(db.Model):
    """SPINS Channel model - channels from SPINS data (includes competitors)"""
    __tablename__ = 'spins_channels'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    short_name = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    spins_data = db.relationship('SpinsData', back_populates='channel')
    
    def __repr__(self):
        return f'<SpinsChannel {self.name}>'


class SpinsBrand(db.Model):
    """SPINS Brand model - brands from SPINS data (includes competitors)"""
    __tablename__ = 'spins_brands'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    short_name = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    spins_data = db.relationship('SpinsData', back_populates='brand')
    
    def __repr__(self):
        return f'<SpinsBrand {self.name}>'


class SpinsItem(db.Model):
    """SPINS Item model - items from SPINS data (includes competitors)"""
    __tablename__ = 'spins_items'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    short_name = db.Column(db.String(100), nullable=True)
    upc = db.Column(db.String(50), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Scraping fields
    img_url = db.Column(db.String(500), nullable=True)
    scrapped_name = db.Column(db.String(500), nullable=True)
    scrapped_url = db.Column(db.String(500), nullable=True)
    scrapped_json = db.Column(db.Text, nullable=True)
    scrapped_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    spins_data = db.relationship('SpinsData', back_populates='item')
    
    # Index for faster queries
    __table_args__ = (
        db.Index('idx_spins_item_upc', 'upc'),
    )
    
    def __repr__(self):
        return f'<SpinsItem {self.upc} - {self.name}>'


class SpinsData(db.Model):
    """SPINS data model - weekly financial data"""
    __tablename__ = 'spins_data'
    
    id = db.Column(db.Integer, primary_key=True)
    week = db.Column(db.Date, nullable=False)  # Week ending date
    channel_id = db.Column(db.Integer, db.ForeignKey('spins_channels.id'), nullable=False)
    brand_id = db.Column(db.Integer, db.ForeignKey('spins_brands.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('spins_items.id'), nullable=False)
    stores_total = db.Column(db.Integer, nullable=False, default=0)
    stores_selling = db.Column(db.Numeric(10, 1), nullable=False, default=0)
    revenues = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    units = db.Column(db.Integer, nullable=False, default=0)
    arp = db.Column(db.Numeric(10, 2), nullable=True)  # Average Retail Price
    average_weekly_revenues_per_selling_item = db.Column(db.Numeric(12, 2), nullable=True)
    average_weekly_units_per_selling_item = db.Column(db.Numeric(10, 2), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    channel = db.relationship('SpinsChannel', back_populates='spins_data')
    brand = db.relationship('SpinsBrand', back_populates='spins_data')
    item = db.relationship('SpinsItem', back_populates='spins_data')
    
    # Index for faster queries
    __table_args__ = (
        db.Index('idx_spins_week', 'week'),
        db.Index('idx_spins_channel_week', 'channel_id', 'week'),
        db.Index('idx_spins_brand_week', 'brand_id', 'week'),
        db.Index('idx_spins_item_week', 'item_id', 'week'),
        db.UniqueConstraint('week', 'channel_id', 'brand_id', 'item_id', name='uq_spins_unique'),
    )
    
    def __repr__(self):
        return f'<SpinsData {self.week} - Channel: {self.channel_id}, Item: {self.item_id}>'


class CrmTicketType(db.Model):
    """CRM Ticket Type model"""
    __tablename__ = 'crm_ticket_types'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    tickets = db.relationship('CrmTicket', back_populates='ticket_type', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<CrmTicketType {self.name}>'


class CrmTicket(db.Model):
    """CRM Ticket model"""
    __tablename__ = 'crm_tickets'
    
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('channel_customers.id'), nullable=False)
    ticket_type_id = db.Column(db.Integer, db.ForeignKey('crm_ticket_types.id'), nullable=True)
    status = db.Column(db.Enum('opened', 'closed', name='ticket_status'), nullable=False, default='opened')
    description = db.Column(db.Text, nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    customer = db.relationship('ChannelCustomer', backref='crm_tickets')
    ticket_type = db.relationship('CrmTicketType', back_populates='tickets')
    creator = db.relationship('User', foreign_keys=[creator_id], backref='created_tickets')
    owner = db.relationship('User', foreign_keys=[owner_id], backref='owned_tickets')
    
    # Indexes for faster queries
    __table_args__ = (
        db.Index('idx_crm_ticket_customer', 'customer_id'),
        db.Index('idx_crm_ticket_status', 'status'),
        db.Index('idx_crm_ticket_due_date', 'due_date'),
    )
    
    def __repr__(self):
        return f'<CrmTicket {self.id} - {self.status}>'

