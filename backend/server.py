from fastapi import FastAPI, APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
from passlib.context import CryptContext
import jwt

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

JWT_SECRET = os.environ.get('JWT_SECRET', 'stacko-robo-secret-key-2026')
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: EmailStr
    name: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user: User

class Category(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class CategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None

class Product(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    sku: str
    category: str
    quantity: int
    unit_price: float
    reorder_level: int
    description: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ProductCreate(BaseModel):
    name: str
    sku: str
    category: str
    quantity: int
    unit_price: float
    reorder_level: int = 10
    description: Optional[str] = None

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    sku: Optional[str] = None
    category: Optional[str] = None
    quantity: Optional[int] = None
    unit_price: Optional[float] = None
    reorder_level: Optional[int] = None
    description: Optional[str] = None

class DashboardStats(BaseModel):
    total_products: int
    total_categories: int
    low_stock_count: int
    total_stock_value: float
    total_quantity: int

class StockDistribution(BaseModel):
    category: str
    count: int
    total_value: float

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    try:
        token = credentials.credentials
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return User(**user)

@api_router.post("/auth/register", response_model=Token)
async def register(user_data: UserCreate):
    existing_user = await db.users.find_one({"email": user_data.email}, {"_id": 0})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user = User(
        email=user_data.email,
        name=user_data.name
    )
    
    user_dict = user.model_dump()
    user_dict["password_hash"] = get_password_hash(user_data.password)
    
    await db.users.insert_one(user_dict)
    
    access_token = create_access_token(data={"sub": user.id})
    return Token(access_token=access_token, token_type="bearer", user=user)

@api_router.post("/auth/login", response_model=Token)
async def login(credentials: UserLogin):
    user = await db.users.find_one({"email": credentials.email}, {"_id": 0})
    if not user or not verify_password(credentials.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    user_obj = User(**user)
    access_token = create_access_token(data={"sub": user_obj.id})
    return Token(access_token=access_token, token_type="bearer", user=user_obj)

@api_router.get("/auth/me", response_model=User)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user

@api_router.get("/categories", response_model=List[Category])
async def get_categories(current_user: User = Depends(get_current_user)):
    categories = await db.categories.find({}, {"_id": 0}).to_list(1000)
    return categories

@api_router.post("/categories", response_model=Category)
async def create_category(category_data: CategoryCreate, current_user: User = Depends(get_current_user)):
    existing = await db.categories.find_one({"name": category_data.name}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Category already exists")
    
    category = Category(**category_data.model_dump())
    await db.categories.insert_one(category.model_dump())
    return category

@api_router.get("/products", response_model=List[Product])
async def get_products(
    category: Optional[str] = None,
    low_stock: Optional[bool] = None,
    current_user: User = Depends(get_current_user)
):
    query = {}
    if category:
        query["category"] = category
    
    products = await db.products.find(query, {"_id": 0}).to_list(1000)
    
    if low_stock:
        products = [p for p in products if p["quantity"] <= p["reorder_level"]]
    
    return products

@api_router.post("/products", response_model=Product)
async def create_product(product_data: ProductCreate, current_user: User = Depends(get_current_user)):
    existing = await db.products.find_one({"sku": product_data.sku}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="SKU already exists")
    
    product = Product(**product_data.model_dump())
    await db.products.insert_one(product.model_dump())
    return product

@api_router.put("/products/{product_id}", response_model=Product)
async def update_product(
    product_id: str,
    product_data: ProductUpdate,
    current_user: User = Depends(get_current_user)
):
    existing = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Product not found")
    
    update_data = {k: v for k, v in product_data.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    if "sku" in update_data and update_data["sku"] != existing["sku"]:
        sku_exists = await db.products.find_one({"sku": update_data["sku"], "id": {"$ne": product_id}}, {"_id": 0})
        if sku_exists:
            raise HTTPException(status_code=400, detail="SKU already exists")
    
    await db.products.update_one({"id": product_id}, {"$set": update_data})
    
    updated_product = await db.products.find_one({"id": product_id}, {"_id": 0})
    return Product(**updated_product)

@api_router.delete("/products/{product_id}")
async def delete_product(product_id: str, current_user: User = Depends(get_current_user)):
    result = await db.products.delete_one({"id": product_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"message": "Product deleted successfully"}

@api_router.get("/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats(current_user: User = Depends(get_current_user)):
    products = await db.products.find({}, {"_id": 0}).to_list(1000)
    categories_count = await db.categories.count_documents({})
    
    total_products = len(products)
    low_stock_count = sum(1 for p in products if p["quantity"] <= p["reorder_level"])
    total_stock_value = sum(p["quantity"] * p["unit_price"] for p in products)
    total_quantity = sum(p["quantity"] for p in products)
    
    return DashboardStats(
        total_products=total_products,
        total_categories=categories_count,
        low_stock_count=low_stock_count,
        total_stock_value=total_stock_value,
        total_quantity=total_quantity
    )

@api_router.get("/dashboard/stock-distribution", response_model=List[StockDistribution])
async def get_stock_distribution(current_user: User = Depends(get_current_user)):
    products = await db.products.find({}, {"_id": 0}).to_list(1000)
    
    distribution = {}
    for product in products:
        category = product["category"]
        if category not in distribution:
            distribution[category] = {"count": 0, "total_value": 0}
        distribution[category]["count"] += 1
        distribution[category]["total_value"] += product["quantity"] * product["unit_price"]
    
    return [
        StockDistribution(category=cat, count=data["count"], total_value=data["total_value"])
        for cat, data in distribution.items()
    ]

@api_router.post("/seed-data")
async def seed_data():
    existing_categories = await db.categories.count_documents({})
    if existing_categories > 0:
        return {"message": "Data already seeded"}
    
    categories = [
        {"id": str(uuid.uuid4()), "name": "Electronics", "description": "Electronic devices and accessories", "created_at": datetime.now(timezone.utc).isoformat()},
        {"id": str(uuid.uuid4()), "name": "Furniture", "description": "Office and home furniture", "created_at": datetime.now(timezone.utc).isoformat()},
        {"id": str(uuid.uuid4()), "name": "Stationery", "description": "Office supplies and stationery", "created_at": datetime.now(timezone.utc).isoformat()},
        {"id": str(uuid.uuid4()), "name": "Clothing", "description": "Apparel and accessories", "created_at": datetime.now(timezone.utc).isoformat()},
        {"id": str(uuid.uuid4()), "name": "Food & Beverages", "description": "Food items and drinks", "created_at": datetime.now(timezone.utc).isoformat()}
    ]
    await db.categories.insert_many(categories)
    
    products = [
        {"id": str(uuid.uuid4()), "name": "Laptop Dell XPS 15", "sku": "ELEC-001", "category": "Electronics", "quantity": 25, "unit_price": 1299.99, "reorder_level": 10, "description": "High-performance laptop", "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()},
        {"id": str(uuid.uuid4()), "name": "Wireless Mouse", "sku": "ELEC-002", "category": "Electronics", "quantity": 150, "unit_price": 29.99, "reorder_level": 50, "description": "Ergonomic wireless mouse", "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()},
        {"id": str(uuid.uuid4()), "name": "Office Chair Premium", "sku": "FURN-001", "category": "Furniture", "quantity": 8, "unit_price": 299.99, "reorder_level": 15, "description": "Ergonomic office chair", "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()},
        {"id": str(uuid.uuid4()), "name": "Standing Desk", "sku": "FURN-002", "category": "Furniture", "quantity": 12, "unit_price": 499.99, "reorder_level": 10, "description": "Adjustable standing desk", "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()},
        {"id": str(uuid.uuid4()), "name": "Notebook A4", "sku": "STAT-001", "category": "Stationery", "quantity": 500, "unit_price": 3.99, "reorder_level": 100, "description": "Ruled notebook", "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()},
        {"id": str(uuid.uuid4()), "name": "Ballpoint Pens (Pack of 10)", "sku": "STAT-002", "category": "Stationery", "quantity": 5, "unit_price": 5.99, "reorder_level": 50, "description": "Blue ink pens", "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()},
        {"id": str(uuid.uuid4()), "name": "Business Shirt", "sku": "CLTH-001", "category": "Clothing", "quantity": 45, "unit_price": 49.99, "reorder_level": 20, "description": "Formal business shirt", "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()},
        {"id": str(uuid.uuid4()), "name": "Coffee Beans (1kg)", "sku": "FOOD-001", "category": "Food & Beverages", "quantity": 3, "unit_price": 24.99, "reorder_level": 20, "description": "Premium arabica beans", "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()},
        {"id": str(uuid.uuid4()), "name": "Bottled Water (24 pack)", "sku": "FOOD-002", "category": "Food & Beverages", "quantity": 80, "unit_price": 8.99, "reorder_level": 30, "description": "Natural spring water", "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()},
        {"id": str(uuid.uuid4()), "name": "USB-C Cable", "sku": "ELEC-003", "category": "Electronics", "quantity": 200, "unit_price": 12.99, "reorder_level": 80, "description": "2m USB-C charging cable", "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()}
    ]
    await db.products.insert_many(products)
    
    return {"message": "Sample data seeded successfully"}

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()