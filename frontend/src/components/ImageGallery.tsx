'use client';

import { useState, useEffect, useCallback } from 'react';
import { X, ChevronDown, ChevronUp, Download, Trash2, User, BookOpen } from 'lucide-react';
import { imageGenerationApi } from '@/lib/api/index';

interface GeneratedImage {
  id: number;
  story_id: number;
  scene_id?: number;
  character_id?: number;
  image_type: string;
  prompt?: string;
  created_at: string;
}

interface SceneInfo {
  id: number;
  sequence_number: number;
  title?: string;
}

interface CharacterInfo {
  id: number;
  name: string;
}

interface ImageGalleryProps {
  storyId: number;
  isOpen: boolean;
  onClose: () => void;
  scenes?: SceneInfo[];
  characters?: CharacterInfo[];
}

interface SceneImageGroup {
  sceneId: number;
  sceneInfo?: SceneInfo;
  images: GeneratedImage[];
  showAll: boolean;
}

export default function ImageGallery({
  storyId,
  isOpen,
  onClose,
  scenes = [],
  characters = [],
}: ImageGalleryProps) {
  const [loading, setLoading] = useState(true);
  const [characterPortraits, setCharacterPortraits] = useState<GeneratedImage[]>([]);
  const [sceneGroups, setSceneGroups] = useState<SceneImageGroup[]>([]);
  const [imageUrls, setImageUrls] = useState<Record<number, string>>({});
  const [expandedCharacters, setExpandedCharacters] = useState(true);

  // Load all images for the story
  const loadImages = useCallback(async () => {
    if (!storyId) return;

    try {
      setLoading(true);

      // Fetch scene images and character portraits in parallel
      const [allImages, portraits] = await Promise.all([
        imageGenerationApi.getStoryImages(storyId),
        imageGenerationApi.getStoryPortraits(storyId).catch(() => []),
      ]);

      // Filter scene images only (not character portraits from this story)
      const sceneImages = allImages.filter(
        img => img.image_type !== 'character_portrait' && img.scene_id
      );

      setCharacterPortraits(portraits);

      // Group scene images by scene_id, sorted by created_at desc
      const groupMap = new Map<number, GeneratedImage[]>();
      for (const img of sceneImages) {
        if (!img.scene_id) continue;
        const existing = groupMap.get(img.scene_id) || [];
        existing.push(img);
        groupMap.set(img.scene_id, existing);
      }

      // Sort each group by created_at desc and create SceneImageGroup objects
      const groups: SceneImageGroup[] = [];
      for (const [sceneId, images] of groupMap.entries()) {
        const sortedImages = images.sort(
          (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        );
        const sceneInfo = scenes.find(s => s.id === sceneId);
        groups.push({
          sceneId,
          sceneInfo,
          images: sortedImages,
          showAll: false,
        });
      }

      // Sort groups by scene sequence number
      groups.sort((a, b) => {
        const seqA = a.sceneInfo?.sequence_number ?? 0;
        const seqB = b.sceneInfo?.sequence_number ?? 0;
        return seqA - seqB;
      });

      setSceneGroups(groups);

      // Load image URLs for visible images (latest per scene + all portraits)
      const imagesToLoad: number[] = [
        ...portraits.map(p => p.id),
        ...groups.map(g => g.images[0]?.id).filter(Boolean),
      ];

      const urls: Record<number, string> = {};
      await Promise.all(
        imagesToLoad.map(async (id) => {
          try {
            const url = await imageGenerationApi.getImageFileAsBlob(id);
            urls[id] = url;
          } catch (err) {
            console.error(`Failed to load image ${id}:`, err);
          }
        })
      );
      setImageUrls(urls);
    } catch (err) {
      console.error('Failed to load gallery images:', err);
    } finally {
      setLoading(false);
    }
  }, [storyId, scenes]);

  useEffect(() => {
    if (isOpen) {
      loadImages();
    }
  }, [isOpen, loadImages]);

  // Load additional image URLs when expanding a scene group
  const loadGroupImages = async (group: SceneImageGroup) => {
    const newUrls: Record<number, string> = { ...imageUrls };
    const idsToLoad = group.images.slice(1).map(img => img.id).filter(id => !imageUrls[id]);

    await Promise.all(
      idsToLoad.map(async (id) => {
        try {
          const url = await imageGenerationApi.getImageFileAsBlob(id);
          newUrls[id] = url;
        } catch (err) {
          console.error(`Failed to load image ${id}:`, err);
        }
      })
    );
    setImageUrls(newUrls);
  };

  const toggleSceneExpand = async (sceneId: number) => {
    setSceneGroups(prev =>
      prev.map(g => {
        if (g.sceneId === sceneId) {
          const newShowAll = !g.showAll;
          if (newShowAll) {
            loadGroupImages(g);
          }
          return { ...g, showAll: newShowAll };
        }
        return g;
      })
    );
  };

  const handleDownload = async (imageId: number, filename: string) => {
    const url = imageUrls[imageId];
    if (!url) return;

    try {
      const response = await fetch(url);
      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(downloadUrl);
    } catch (err) {
      console.error('Failed to download image:', err);
    }
  };

  const handleDelete = async (imageId: number) => {
    if (!confirm('Delete this image?')) return;

    try {
      await imageGenerationApi.deleteImage(imageId);
      // Refresh gallery
      loadImages();
    } catch (err) {
      console.error('Failed to delete image:', err);
    }
  };

  const getCharacterName = (characterId?: number) => {
    if (!characterId) return 'Unknown Character';
    const char = characters.find(c => c.id === characterId);
    return char?.name || 'Unknown Character';
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm">
      <div className="relative w-full max-w-5xl max-h-[90vh] mx-4 bg-gray-900 rounded-xl shadow-2xl overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/10">
          <h2 className="text-xl font-semibold text-white">Image Gallery</h2>
          <button
            onClick={onClose}
            className="p-2 text-white/60 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="w-8 h-8 border-2 border-purple-400/30 border-t-purple-400 rounded-full animate-spin" />
            </div>
          ) : (
            <div className="space-y-8">
              {/* Character Portraits Section */}
              {characterPortraits.length > 0 && (
                <div>
                  <button
                    onClick={() => setExpandedCharacters(!expandedCharacters)}
                    className="flex items-center gap-2 mb-4 text-lg font-medium text-white/90 hover:text-white"
                  >
                    <User className="w-5 h-5 text-purple-400" />
                    <span>Character Portraits ({characterPortraits.length})</span>
                    {expandedCharacters ? (
                      <ChevronUp className="w-4 h-4 text-white/50" />
                    ) : (
                      <ChevronDown className="w-4 h-4 text-white/50" />
                    )}
                  </button>

                  {expandedCharacters && (
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
                      {characterPortraits.map((img) => (
                        <div key={img.id} className="group relative">
                          <div className="aspect-square rounded-lg overflow-hidden bg-gray-800">
                            {imageUrls[img.id] ? (
                              <img
                                src={imageUrls[img.id]}
                                alt={getCharacterName(img.character_id)}
                                className="w-full h-full object-cover"
                              />
                            ) : (
                              <div className="w-full h-full flex items-center justify-center">
                                <div className="w-6 h-6 border-2 border-purple-400/30 border-t-purple-400 rounded-full animate-spin" />
                              </div>
                            )}
                          </div>
                          <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity rounded-lg flex items-center justify-center gap-2">
                            <button
                              onClick={() => handleDownload(img.id, `portrait_${img.character_id}.png`)}
                              className="p-2 bg-white/20 hover:bg-white/30 rounded-lg"
                              title="Download"
                            >
                              <Download className="w-4 h-4 text-white" />
                            </button>
                            <button
                              onClick={() => handleDelete(img.id)}
                              className="p-2 bg-red-500/20 hover:bg-red-500/30 rounded-lg"
                              title="Delete"
                            >
                              <Trash2 className="w-4 h-4 text-red-400" />
                            </button>
                          </div>
                          <p className="mt-2 text-sm text-white/70 truncate">
                            {getCharacterName(img.character_id)}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Scene Images Section */}
              {sceneGroups.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-4 text-lg font-medium text-white/90">
                    <BookOpen className="w-5 h-5 text-blue-400" />
                    <span>Scene Images</span>
                  </div>

                  <div className="space-y-6">
                    {sceneGroups.map((group) => (
                      <div key={group.sceneId} className="bg-white/5 rounded-lg p-4">
                        {/* Scene Header */}
                        <div className="flex items-center justify-between mb-3">
                          <h3 className="text-sm font-medium text-white/80">
                            Scene {group.sceneInfo?.sequence_number || '?'}
                            {group.sceneInfo?.title && (
                              <span className="text-white/50 ml-2">- {group.sceneInfo.title}</span>
                            )}
                          </h3>
                          {group.images.length > 1 && (
                            <button
                              onClick={() => toggleSceneExpand(group.sceneId)}
                              className="flex items-center gap-1 text-xs text-purple-400 hover:text-purple-300"
                            >
                              {group.showAll ? (
                                <>
                                  <span>Hide older images</span>
                                  <ChevronUp className="w-3 h-3" />
                                </>
                              ) : (
                                <>
                                  <span>Show {group.images.length - 1} other image{group.images.length > 2 ? 's' : ''}</span>
                                  <ChevronDown className="w-3 h-3" />
                                </>
                              )}
                            </button>
                          )}
                        </div>

                        {/* Images Grid */}
                        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
                          {(group.showAll ? group.images : group.images.slice(0, 1)).map((img, idx) => (
                            <div key={img.id} className="group relative">
                              <div className="aspect-video rounded-lg overflow-hidden bg-gray-800">
                                {imageUrls[img.id] ? (
                                  <img
                                    src={imageUrls[img.id]}
                                    alt={`Scene ${group.sceneInfo?.sequence_number || '?'} image`}
                                    className="w-full h-full object-cover"
                                  />
                                ) : (
                                  <div className="w-full h-full flex items-center justify-center">
                                    <div className="w-6 h-6 border-2 border-purple-400/30 border-t-purple-400 rounded-full animate-spin" />
                                  </div>
                                )}
                              </div>
                              <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity rounded-lg flex items-center justify-center gap-2">
                                <button
                                  onClick={() => handleDownload(img.id, `scene_${group.sceneInfo?.sequence_number || group.sceneId}_${idx + 1}.png`)}
                                  className="p-2 bg-white/20 hover:bg-white/30 rounded-lg"
                                  title="Download"
                                >
                                  <Download className="w-4 h-4 text-white" />
                                </button>
                                <button
                                  onClick={() => handleDelete(img.id)}
                                  className="p-2 bg-red-500/20 hover:bg-red-500/30 rounded-lg"
                                  title="Delete"
                                >
                                  <Trash2 className="w-4 h-4 text-red-400" />
                                </button>
                              </div>
                              {idx === 0 && group.images.length > 1 && !group.showAll && (
                                <div className="absolute bottom-2 right-2 px-2 py-1 bg-black/60 rounded text-xs text-white/70">
                                  Latest
                                </div>
                              )}
                              {group.showAll && (
                                <p className="mt-1 text-xs text-white/50">
                                  {new Date(img.created_at).toLocaleDateString()}
                                </p>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Empty State */}
              {characterPortraits.length === 0 && sceneGroups.length === 0 && (
                <div className="text-center py-12">
                  <BookOpen className="w-12 h-12 text-white/20 mx-auto mb-4" />
                  <p className="text-white/50">No images generated yet</p>
                  <p className="text-sm text-white/30 mt-1">
                    Generate images for your scenes using the image button on each scene
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
