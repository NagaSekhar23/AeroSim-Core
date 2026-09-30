#include "ExclusiveFile.h"

#include <cerrno>
#include <cstring>
#include <stdexcept>

ExclusiveFile::ExclusiveFile(const std::string& path) : path_(path) {
    // C11's exclusive-create mode prevents truncating a file that appears
    // between a separate existence check and opening the destination.
    file_ = std::fopen(path.c_str(), "wx");
    if (file_ == nullptr) {
        if (errno == EEXIST) {
            throw std::runtime_error("refusing to overwrite existing output file: " + path);
        }
        throw std::runtime_error("could not create output file " + path + ": "
                                 + std::strerror(errno));
    }
}

ExclusiveFile::~ExclusiveFile() {
    if (file_ != nullptr) {
        std::fclose(file_);
    }
}

void ExclusiveFile::write(const std::string& contents) {
    if (file_ == nullptr) {
        throw std::runtime_error("cannot write to a closed output file: " + path_);
    }
    const std::size_t written = std::fwrite(contents.data(), 1, contents.size(), file_);
    if (written != contents.size()) {
        throw std::runtime_error("failed while writing output file " + path_ + ": "
                                 + std::strerror(errno));
    }
}

void ExclusiveFile::close() {
    if (file_ != nullptr) {
        std::FILE* closing_file = file_;
        file_ = nullptr;
        if (std::fclose(closing_file) != 0) {
            throw std::runtime_error("failed while closing output file " + path_ + ": "
                                     + std::strerror(errno));
        }
    }
}
