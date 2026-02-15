"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Search, SlidersHorizontal } from "lucide-react";

interface ForumSearchBarProps {
  sortBy: 'votes' | 'newest' | 'oldest' | 'views';
  onSortChange: (sort: 'votes' | 'newest' | 'oldest' | 'views') => void;
  onSearch: (search: string, tags: string) => void;
}

export default function ForumSearchBar({ sortBy, onSortChange, onSearch }: ForumSearchBarProps) {
  const [searchInput, setSearchInput] = useState('');
  const [tagsInput, setTagsInput] = useState('');
  const [showFilters, setShowFilters] = useState(false);

  const handleSearch = () => {
    onSearch(searchInput, tagsInput);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  return (
    <div className="bg-white rounded-lg border p-4 space-y-4">
      {/* Search Bar */}
      <div className="flex gap-2">
        <div className="flex-1 relative">
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Tìm kiếm trong tiêu đề và nội dung..."
            className="w-full pl-10 pr-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
          />
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
        </div>
        <Button
          onClick={handleSearch}
          className="bg-blue-600 text-white hover:bg-blue-700"
        >
          Tìm kiếm
        </Button>
        <Button
          onClick={() => setShowFilters(!showFilters)}
          variant="outline"
          className="flex items-center gap-2"
        >
          <SlidersHorizontal className="w-4 h-4" />
          Lọc
        </Button>
      </div>

      {/* Filters */}
      {showFilters && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4 border-t">
          <div>
            <label className="block text-sm font-medium mb-2">Sắp xếp theo</label>
            <select
              value={sortBy}
              onChange={(e) => onSortChange(e.target.value as any)}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
            >
              <option value="votes">Điểm cao nhất</option>
              <option value="newest">Mới nhất</option>
              <option value="oldest">Cũ nhất</option>
              <option value="views">Xem nhiều nhất</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">Lọc theo tags (phân cách bằng dấu phẩy)</label>
            <input
              type="text"
              value={tagsInput}
              onChange={(e) => setTagsInput(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="vd: javascript,react,typescript"
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
            />
          </div>
        </div>
      )}

      {/* Quick Sort Buttons */}
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={() => onSortChange('votes')}
          className={`px-3 py-1.5 text-sm rounded-full transition-colors ${
            sortBy === 'votes'
              ? 'bg-blue-100 text-blue-700 font-medium'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          🔥 Phổ biến
        </button>
        <button
          onClick={() => onSortChange('newest')}
          className={`px-3 py-1.5 text-sm rounded-full transition-colors ${
            sortBy === 'newest'
              ? 'bg-blue-100 text-blue-700 font-medium'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          ⏰ Mới nhất
        </button>
        <button
          onClick={() => onSortChange('views')}
          className={`px-3 py-1.5 text-sm rounded-full transition-colors ${
            sortBy === 'views'
              ? 'bg-blue-100 text-blue-700 font-medium'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          👁️ Xem nhiều
        </button>
      </div>
    </div>
  );
}