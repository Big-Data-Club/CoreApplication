"use client"

import Image from 'next/image';
import Link from 'next/link';
import { FaFacebook, FaTwitter, FaInstagram, FaLinkedin } from 'react-icons/fa';
import bdc from "@/assets/bdclogo.png"

const Footer: React.FC = () => {
  return (
    <footer className="bg-gradient-to-r from-slate-700 to-slate-600 text-gray-200 py-3 sm:py-4 border-t border-slate-600 shadow-lg w-full mt-auto flex-shrink-0">
      <div className="max-w-7xl mx-auto px-3 sm:px-4 md:px-6 lg:px-8">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 sm:gap-4 text-xs sm:text-sm">
          {/* Left: Logo and Name */}
          <Link href="/" className="flex items-center gap-2 hover:text-cyan-300 transition-colors duration-300 order-2 sm:order-1">
            <Image
              src={bdc}
              alt="Big Data Club Logo"
              width={20}
              height={20}
              className="rounded-full"
            />
            <span className="font-semibold hidden sm:inline">Big Data Club Management Site</span>
            <span className="font-semibold sm:hidden">BDC Management</span>
          </Link>

          {/* Center: Copyright */}
          <span className="text-gray-300 text-xs order-3 sm:order-2">
            © 2025 Big Data Club. All rights reserved.
          </span>

          {/* Right: Social Icons */}
          <div className="flex items-center gap-3 sm:gap-4 order-1 sm:order-3">
            <a href="https://facebook.com" target="_blank" rel="noopener noreferrer" className="hover:text-cyan-300 transition-colors duration-300">
              <FaFacebook size={16} />
            </a>
            <a href="https://twitter.com" target="_blank" rel="noopener noreferrer" className="hover:text-cyan-300 transition-colors duration-300">
              <FaTwitter size={16} />
            </a>
            <a href="https://instagram.com" target="_blank" rel="noopener noreferrer" className="hover:text-cyan-300 transition-colors duration-300">
              <FaInstagram size={16} />
            </a>
            <a href="https://linkedin.com" target="_blank" rel="noopener noreferrer" className="hover:text-cyan-300 transition-colors duration-300">
              <FaLinkedin size={16} />
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
};

export default Footer;