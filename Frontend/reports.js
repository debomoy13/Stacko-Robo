import { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { api } from '@/utils/api';
import { toast } from 'sonner';
import { TrendingUp, Package, DollarSign, AlertCircle } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

export default function Reports() {
  const [products, setProducts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [stats, setStats] = useState(null);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [productsRes, categoriesRes, statsRes] = await Promise.all([
        api.get('/products'),
        api.get('/categories'),
        api.get('/dashboard/stats')
      ]);
      setProducts(productsRes.data);
      setCategories(categoriesRes.data);
      setStats(statsRes.data);
    } catch (error) {
      toast.error('Failed to load reports');
    }
  };

  const categoryStats = categories.map((cat) => {
    const categoryProducts = products.filter((p) => p.category === cat.name);
    const totalValue = categoryProducts.reduce((sum, p) => sum + p.quantity * p.unit_price, 0);
    const totalQuantity = categoryProducts.reduce((sum, p) => sum + p.quantity, 0);
    return {
      name: cat.name,
      products: categoryProducts.length,
      value: totalValue,
      quantity: totalQuantity,
    };
  });

  const topProducts = [...products]
    .sort((a, b) => b.quantity * b.unit_price - a.quantity * a.unit_price)
    .slice(0, 5);

  return (
    <div className="space-y-6" data-testid="reports-page">
      <div>
        <h1 className="text-4xl font-bold text-slate-900 mb-2" data-testid="reports-title">Reports & Analytics</h1>
        <p className="text-slate-600">Insights into your inventory</p>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        <Card className="shadow-md">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-600">Total Products</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <div className="text-3xl font-bold text-slate-900">{stats?.total_products || 0}</div>
              <Package className="w-8 h-8 text-blue-600" />
            </div>
            <p className="text-sm text-slate-500 mt-2">Across {stats?.total_categories || 0} categories</p>
          </CardContent>
        </Card>

        <Card className="shadow-md">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-600">Total Stock Value</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <div className="text-3xl font-bold text-slate-900">
                ${(stats?.total_stock_value || 0).toLocaleString()}
              </div>
              <DollarSign className="w-8 h-8 text-green-600" />
            </div>
            <p className="text-sm text-slate-500 mt-2">{stats?.total_quantity || 0} total units</p>
          </CardContent>
        </Card>

        <Card className="shadow-md">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-600">Low Stock Items</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <div className="text-3xl font-bold text-red-600">{stats?.low_stock_count || 0}</div>
              <AlertCircle className="w-8 h-8 text-red-600" />
            </div>
            <p className="text-sm text-slate-500 mt-2">Need immediate attention</p>
          </CardContent>
        </Card>
      </div>

      <Card className="shadow-md">
        <CardHeader>
          <CardTitle>Category Performance</CardTitle>
          <CardDescription>Product count and value by category</CardDescription>
        </CardHeader>
        <CardContent>
          {categoryStats.length > 0 ? (
            <ResponsiveContainer width="100%" height={400}>
              <BarChart data={categoryStats}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis yAxisId="left" />
                <YAxis yAxisId="right" orientation="right" />
                <Tooltip />
                <Legend />
                <Bar yAxisId="left" dataKey="products" fill="#0088FE" name="Product Count" />
                <Bar yAxisId="right" dataKey="value" fill="#00C49F" name="Total Value ($)" />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-center py-12 text-slate-500">No data available</div>
          )}
        </CardContent>
      </Card>

      <Card className="shadow-md">
        <CardHeader>
          <CardTitle className="flex items-center space-x-2">
            <TrendingUp className="w-5 h-5" />
            <span>Top 5 Products by Value</span>
          </CardTitle>
          <CardDescription>Highest value items in inventory</CardDescription>
        </CardHeader>
        <CardContent>
          {topProducts.length > 0 ? (
            <div className="space-y-4">
              {topProducts.map((product, index) => (
                <div
                  key={product.id}
                  className="flex items-center justify-between p-4 bg-slate-50 rounded-lg border border-slate-200"
                  data-testid="top-product-item"
                >
                  <div className="flex items-center space-x-4">
                    <div className="flex items-center justify-center w-10 h-10 bg-primary text-white rounded-full font-bold">
                      {index + 1}
                    </div>
                    <div>
                      <p className="font-medium text-slate-900">{product.name}</p>
                      <p className="text-sm text-slate-600">{product.category}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-lg font-bold text-slate-900">
                      ${(product.quantity * product.unit_price).toLocaleString()}
                    </p>
                    <p className="text-sm text-slate-600">
                      {product.quantity} × ${product.unit_price.toFixed(2)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-slate-500">No products available</div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}